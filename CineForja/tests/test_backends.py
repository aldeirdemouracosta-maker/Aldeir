import json
import os
import stat
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from cineforja.config import Config
from cineforja.orchestrator.graph import build_app
from cineforja.orchestrator.hitl import config_for
from cineforja.orchestrator.parsing import parse_shots
from cineforja.orchestrator.state import new_state
from cineforja.workers import executors
from cineforja.workers.backends import comfyui, ollama, sdcpp
from cineforja.workers.backends.ollama import BackendError
from cineforja.workers.server import WorkerServer


class Fake(ThreadingHTTPServer):
    """Servidor HTTP falso para Ollama/ComfyUI; guarda as requisições recebidas."""
    daemon_threads = True

    def __init__(self, routes):
        super().__init__(("127.0.0.1", 0), self.H)
        self.routes, self.seen = routes, []
        threading.Thread(target=self.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()

    @property
    def url(self):
        return f"http://127.0.0.1:{self.server_address[1]}"

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass

        def _do(self):
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n)) if n else None
            self.server.seen.append((self.command, self.path, body))
            out = self.server.routes[self.path.split("?")[0]](body)
            raw = out if isinstance(out, bytes) else json.dumps(out).encode()
            self.send_response(200); self.send_header("Content-Length", str(len(raw))); self.end_headers()
            self.wfile.write(raw)
        do_GET = do_POST = _do

    def stop(self):
        self.shutdown(); self.server_close()


@pytest.fixture
def fake_ollama():
    def gen(b):
        if b.get("keep_alive") == 0:
            return {"done": True}
        if b.get("format") == "json":
            return {"response": '{"shots": ["plano aberto do robô", "close nas mãos", "robô dança"]}'}
        if b.get("images"):
            return {"response": "8"}
        return {"response": "Plano: tom leve, robô azul."}
    s = Fake({"/api/generate": gen}); yield s; s.stop()


def test_parse_shots():
    assert parse_shots('xx {"shots": ["a", "b", "c", "d"]} yy', 3) == ["a", "b", "c"]
    assert parse_shots('[{"prompt": "a"}, "b"]', 5) == ["a", "b"]
    assert parse_shots("sem json", 3) is None
    assert parse_shots('{"shots": []}', 3) is None


def test_ollama_generate_and_unload(fake_ollama, tmp_path):
    img = tmp_path / "f.png"; img.write_bytes(b"png")
    assert ollama.generate(fake_ollama.url, "m", "oi") == "Plano: tom leve, robô azul."
    assert ollama.generate(fake_ollama.url, "m", "nota", image_path=str(img)) == "8"
    ollama.unload(fake_ollama.url, "m")
    assert fake_ollama.seen[-1][2] == {"model": "m", "keep_alive": 0}
    assert fake_ollama.seen[1][2]["images"]


def test_ollama_down():
    with pytest.raises(BackendError):
        ollama.generate("http://127.0.0.1:9", "m", "x", timeout=1)


def test_comfy_fill_keeps_types():
    wf = {"1": {"inputs": {"text": "{{prompt}}", "seed": "{{seed}}", "n": 4, "l": ["{{prompt}}"]}}}
    out = comfyui.fill(wf, {"prompt": "gato", "seed": 7})
    assert out["1"]["inputs"] == {"text": "gato", "seed": 7, "n": 4, "l": ["gato"]}


@pytest.fixture
def fake_comfy():
    polls = {"n": 0}

    def history(_):
        polls["n"] += 1
        return {} if polls["n"] < 2 else {"p1": {"outputs": {"9": {"images": [
            {"filename": "../../evil.png", "subfolder": "", "type": "output"}]}}}}
    s = Fake({"/prompt": lambda b: {"prompt_id": "p1"}, "/history/p1": history,
              "/view": lambda b: b"PNGDATA", "/free": lambda b: {}})
    yield s; s.stop()


def test_comfy_run_workflow(fake_comfy, tmp_path):
    wf = tmp_path / "wf.json"; wf.write_text(json.dumps({"1": {"inputs": {"text": "{{prompt}}"}}}))
    out = tmp_path / "out"
    files = comfyui.run_workflow(fake_comfy.url, str(wf), {"prompt": "robô"}, str(out), poll=0.01)
    assert files == [str(out / "evil.png")]  # basename: sem path traversal
    assert open(files[0], "rb").read() == b"PNGDATA"
    assert fake_comfy.seen[0][2]["prompt"]["1"]["inputs"]["text"] == "robô"


def test_comfy_timeout(tmp_path):
    s = Fake({"/prompt": lambda b: {"prompt_id": "p"}, "/history/p": lambda b: {}})
    wf = tmp_path / "wf.json"; wf.write_text("{}")
    try:
        with pytest.raises(BackendError):
            comfyui.run_workflow(s.url, str(wf), {}, str(tmp_path), timeout=0.2, poll=0.05)
    finally:
        s.stop()


def fake_sd(tmp_path, ok=True):
    p = tmp_path / "sd"
    p.write_text("#!/bin/sh\nwhile [ $# -gt 0 ]; do [ \"$1\" = -o ] && out=$2; shift; done\n"
                 + ('echo img > "$out"\n' if ok else "echo erro >&2; exit 3\n"))
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return str(p)


def test_sdcpp(tmp_path):
    out = tmp_path / "o" / "a.png"
    assert sdcpp.generate(fake_sd(tmp_path), "m.gguf", "gato", str(out)) == str(out)
    with pytest.raises(BackendError):
        sdcpp.generate(fake_sd(tmp_path, ok=False), "m", "x", str(tmp_path / "b.png"))


def test_out_dir_blocks_traversal(tmp_path):
    cfg = Config(output_dir=str(tmp_path))
    with pytest.raises(BackendError):
        executors._out_dir(cfg, {"project_id": "../../etc"})


def test_score_parse():
    assert executors._score("Nota: 7,5") == 0.75
    assert executors._score("15") == 1.0
    with pytest.raises(BackendError):
        executors._score("não sei")


def run_server(kind, cfg):
    srv = WorkerServer(kind, cfg=cfg)
    threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()
    return srv


def test_full_graph_with_real_executors(fake_ollama, fake_comfy, tmp_path, monkeypatch):
    wf = tmp_path / "wf.json"; wf.write_text(json.dumps({"1": {"inputs": {"text": "{{prompt}}"}}}))
    cfg = Config(ollama_url=fake_ollama.url, llm_model="llm-x", vlm_model="vlm-x", comfy_url=fake_comfy.url,
                 comfy_workflow_video=str(wf), output_dir=str(tmp_path / "proj"))
    cuda, vulkan = run_server("cuda", cfg), run_server("vulkan", cfg)
    monkeypatch.setenv("CINEFORJA_WORKERS", f"cuda={cuda.url},vulkan={vulkan.url}")
    try:
        app = build_app(str(tmp_path / "g.db"), interrupt_before=[])
        st = app.invoke(new_state("g1", "robô dança"), config_for("g1"))
    finally:
        cuda.shutdown(); vulkan.shutdown()
    assert [s["prompt"] for s in st["storyboard"]] == ["plano aberto do robô", "close nas mãos", "robô dança"]
    assert st["plan"].startswith("Plano: tom leve")
    assert all(s["score"] == 0.8 and s["status"] == "done" for s in st["storyboard"])
    assert all(os.path.isfile(s["frames_path"]) for s in st["storyboard"])
    # Ollama e ComfyUI dividem a P100: ao trocar de serviço, o anterior é descarregado
    hist = cuda.slot.history
    assert ("unload", "ollama:llm-x") in hist and ("unload", "comfyui") in hist
    assert any(b == {"model": "llm-x", "keep_alive": 0} for _, _, b in fake_ollama.seen)
    assert any(path == "/free" for _, path, _ in fake_comfy.seen)


def test_worker_returns_502_on_backend_failure(tmp_path, monkeypatch):
    cfg = Config(ollama_url="http://127.0.0.1:9", llm_model="m")
    srv = run_server("cuda", cfg)
    monkeypatch.setenv("CINEFORJA_WORKERS", f"cuda={srv.url}")
    from cineforja.workers.client import WorkerError, call
    try:
        with pytest.raises(WorkerError, match="recusou"):
            call("llm", "x", {"prompt": "oi"})
    finally:
        srv.shutdown()
