"""Servidores falsos que seguem os contratos DOCUMENTADOS do Ollama e da API compatível com OpenAI
(llama-server, LM Studio). Falam HTTP de verdade (soquete real) e registram o que receberam."""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CHAT = "qwen2.5:0.5b"
CODER = "qwen2.5-coder:0.5b"
EMBED = "nomic-embed-text:latest"


def llm(model: str, prompt: str, system: str = "") -> str:
    """'Modelo' determinístico: o suficiente para exercitar o contrato."""
    if "SOMENTE com o código" in system or "Gere código" in system:
        return "def soma(a, b):\n    return a + b\n"
    if "Resuma" in system:
        return "Resumo: lançamento em março."
    if "Traduza" in system:
        return "Good morning, how are you?"
    if "array JSON" in system:
        return json.dumps([{"action": "lang_detect", "payload": {"text": "The cat is on the table"}}])
    return "ok"


def embed(text: str) -> list[float]:
    t = text.lower()
    return [float(any(w in t for w in ("gato", "felino", "dorme", "animal"))),
            float(any(w in t for w in ("carro", "veículo", "motor", "estrada"))), 0.1]


class _Base(BaseHTTPRequestHandler):
    log: list[dict] = []

    def log_message(self, *a):  # silencioso
        pass

    def _json(self, code: int, obj) -> None:
        raw = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b""
        ctype = self.headers.get("Content-Type", "")
        return json.loads(raw) if raw and ctype.startswith("application/json") else {"_raw": raw, "_ctype": ctype}

    def do_GET(self):
        self.server.requests.append({"method": "GET", "path": self.path})
        self.get()

    def do_POST(self):
        body = self._body()
        self.server.requests.append({"method": "POST", "path": self.path, "body": body})
        self.post(body)


class OllamaHandler(_Base):
    def get(self):
        if self.path == "/api/tags":
            self._json(200, {"models": [{"name": m, "model": m} for m in (CHAT, CODER, EMBED)]})
        elif self.path == "/api/ps":
            self._json(200, {"models": [{"name": CHAT, "model": CHAT, "size_vram": 0}]})
        else:
            self._json(404, {"error": "not found"})

    def post(self, b):
        if self.path == "/api/generate":
            if b.get("stream") is not False:
                return self._json(400, {"error": "este teste exige stream=false"})
            self._json(200, {"model": b["model"], "response": llm(b["model"], b["prompt"], b.get("system", "")), "done": True})
        elif self.path == "/api/embed":
            ins = b["input"] if isinstance(b["input"], list) else [b["input"]]
            self._json(200, {"model": b["model"], "embeddings": [embed(t) for t in ins]})
        else:
            self._json(404, {"error": "not found"})


class OpenAIHandler(_Base):
    def get(self):
        if self.path == "/v1/models":
            self._json(200, {"object": "list", "data": [{"id": m, "object": "model"} for m in (CHAT, CODER, EMBED)]})
        else:
            self._json(404, {"error": {"message": "not found"}})

    def post(self, b):
        if self.path == "/v1/chat/completions":
            msgs = b["messages"]
            system = next((m["content"] for m in msgs if m["role"] == "system"), "")
            user = msgs[-1]["content"]
            text = user if isinstance(user, str) else next(p["text"] for p in user if p["type"] == "text")
            self._json(200, {"choices": [{"index": 0, "message": {"role": "assistant",
                                                                    "content": llm(b["model"], text, system)}}]})
        elif self.path == "/v1/embeddings":
            self._json(200, {"object": "list", "data": [{"index": 0, "embedding": embed(b["input"])}]})
        else:
            self._json(404, {"error": {"message": "not found"}})


class Server:
    def __init__(self, handler):
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.httpd.requests = []
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.httpd.server_address[1]}"

    @property
    def requests(self) -> list[dict]:
        return self.httpd.requests

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()
