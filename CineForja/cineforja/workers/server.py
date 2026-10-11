"""Worker HTTP local (um processo por GPU).

    python -m cineforja.workers.server --kind cuda   --port 8101
    python -m cineforja.workers.server --kind vulkan --port 8102

Escuta apenas em 127.0.0.1. Fase 2: o backend é simulado; os modelos reais entram na Fase 3.
"""
from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .. import config as _config
from . import executors
from .backends.ollama import BackendError
from .router import choose_worker
from .slot import Backend, MockBackend, ModelSlot

# Modelo pesado associado a cada tipo de tarefa (nomes provisórios até a Fase 3).
MODEL_FOR_TASK = {
    "llm": "llm", "video": "video", "heavy_image": "image-heavy", "consistency": "vlm",
    "light_image": "image-light", "audio": "audio", "upscale": "upscale",
}
MAX_BODY = 1 << 20


class WorkerServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 128  # o padrão (5) derruba conexões em rajadas de pedidos

    def __init__(self, kind: str, port: int = 0, backend: Backend | None = None,
                 cfg: _config.Config | None = None) -> None:
        super().__init__(("127.0.0.1", port), _Handler)
        self.kind = kind
        self.cfg = cfg or _config.Config()
        self.executors = executors.build(self.cfg)
        real = bool(self.executors)
        self.backend = backend or (executors.GpuBackend(self.cfg) if real else MockBackend())
        self.slot = ModelSlot(self.backend)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}"


class _Handler(BaseHTTPRequestHandler):
    server: WorkerServer

    def log_message(self, *args) -> None:  # silencia o log padrão
        pass

    def _send(self, code: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send(200, {"ok": True, "kind": self.server.kind})
        elif self.path == "/status":
            self._send(200, {"kind": self.server.kind, "loaded": self.server.slot.loaded,
                             "history": self.server.slot.history})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path == "/unload":
            self.server.slot.unload()
            return self._send(200, {"ok": True})
        if self.path != "/run":
            return self._send(404, {"error": "not found"})
        length = int(self.headers.get("Content-Length", 0))
        if length > MAX_BODY:
            return self._send(413, {"error": "payload too large"})
        try:
            req = json.loads(self.rfile.read(length) or b"{}")
            task, what = req["task_type"], str(req.get("what", ""))
        except (ValueError, KeyError):
            return self._send(400, {"error": "invalid request"})
        if choose_worker(task) != self.server.kind:
            return self._send(400, {"error": f"task '{task}' does not belong to worker '{self.server.kind}'"})
        fn = self.server.executors.get(task)
        model = (executors.model_name(task, self.server.cfg) if fn else None) or MODEL_FOR_TASK.get(task, "cpu")
        payload = req.get("payload") or {}
        try:
            result = self.server.slot.run(model, (lambda m: fn(payload)) if fn else (lambda m: None))
        except (BackendError, KeyError, OSError) as exc:
            return self._send(502, {"error": str(exc)})
        self._send(200, {"log": f"[{self.server.kind}] {what}", "model": model, "result": result})


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--kind", choices=["cuda", "vulkan", "cpu"], required=True)
    p.add_argument("--port", type=int, required=True)
    args = p.parse_args(argv)
    srv = WorkerServer(args.kind, args.port, cfg=_config.load())
    print(f"worker {args.kind} em {srv.url}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
