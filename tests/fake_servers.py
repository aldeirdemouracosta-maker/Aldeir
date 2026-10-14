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


def chat_llm(messages: list[dict]) -> str:
    """'Modelo' com memória: só lembra o nome se ele estiver no HISTÓRICO que recebeu."""
    import re
    *prev, last = messages
    if "?" in last["content"] and "nome" in last["content"].lower():          # é uma pergunta sobre o nome
        for m in prev:
            hit = re.search(r"meu nome é (\w+)", m["content"], re.I) if m["role"] == "user" else None
            if hit:
                return f"Seu nome é {hit.group(1)}."
        return "Não sei seu nome."
    return f"Prazer! ({len(prev)} mensagens de contexto)"


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
        elif self.path == "/api/chat":
            if b.get("stream") is not False or not b.get("messages"):
                return self._json(400, {"error": "stream=false e messages são obrigatórios"})
            self._json(200, {"model": b["model"], "message": {"role": "assistant", "content": chat_llm(b["messages"])},
                             "done": True})
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
            convo = [m for m in msgs if m["role"] != "system"]
            reply = chat_llm(convo) if len(convo) > 1 else llm(b["model"], text, system)
            self._json(200, {"choices": [{"index": 0, "message": {"role": "assistant", "content": reply}}]})
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


# ---------- mídia ----------
import base64  # noqa: E402
import io  # noqa: E402
import wave  # noqa: E402
from email.parser import BytesParser  # noqa: E402
from email.policy import default  # noqa: E402


def parse_multipart(ctype: str, raw: bytes) -> dict[str, tuple[str | None, bytes]]:
    """campo -> (nome do arquivo ou None, conteúdo). Falha se o multipart estiver malformado."""
    msg = BytesParser(policy=default).parsebytes(b"Content-Type: " + ctype.encode() + b"\r\n\r\n" + raw)
    assert msg.is_multipart(), "corpo não é multipart"
    return {p.get_param("name", header="content-disposition"): (p.get_filename(), p.get_payload(decode=True))
            for p in msg.iter_parts()}


def wav_bytes(seconds: float = 0.1, rate: int = 8000) -> bytes:
    import math
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(b"".join(int(8000 * math.sin(2 * math.pi * 440 * i / rate)).to_bytes(2, "little", signed=True)
                               for i in range(int(seconds * rate))))
    return buf.getvalue()


class AudioHandler(_Base):
    """STT/TTS no contrato OpenAI. reject_verbose=True imita servidor sem verbose_json."""
    reject_verbose = False

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b""
        ctype = self.headers.get("Content-Type", "")
        if ctype.startswith("application/json"):
            return json.loads(raw)
        return {"_multipart": parse_multipart(ctype, raw) if ctype.startswith("multipart/form-data") else None}

    def get(self):
        if self.path == "/v1/models":
            self._json(200, {"data": [{"id": "whisper-small"}, {"id": "kokoro"}]})
        else:
            self._json(404, {})

    def post(self, b):
        if self.path == "/v1/audio/transcriptions":
            parts = b["_multipart"]
            if parts is None or "file" not in parts or not parts["file"][1].startswith(b"RIFF"):
                return self._json(400, {"error": "file ausente ou inválido"})
            fmt = parts["response_format"][1].decode()
            if fmt == "verbose_json" and self.reject_verbose:
                return self._json(400, {"error": "response_format não suportado"})
            out = {"text": " olá mundo "}
            if fmt == "verbose_json":
                out["language"] = "portuguese"
            self._json(200, out)
        elif self.path == "/v1/audio/speech":
            if b.get("response_format") != "wav" or not b.get("input") or not b.get("voice"):
                return self._json(400, {"error": "parâmetros inválidos"})
            raw = wav_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        else:
            self._json(404, {})


class AudioNoVerboseHandler(AudioHandler):
    reject_verbose = True


class VisionHandler(OpenAIHandler):
    """llama-server com mmproj: valida o data URI recebido e descreve."""

    def post(self, b):
        if self.path != "/v1/chat/completions":
            return super().post(b)
        parts = b["messages"][-1]["content"]
        img = next((p for p in parts if p["type"] == "image_url"), None)
        prompt = next(p["text"] for p in parts if p["type"] == "text")
        if img is None:
            return self._json(400, {"error": "sem imagem"})
        head, _, data = img["image_url"]["url"].partition(",")
        assert head in ("data:image/png;base64", "data:image/jpeg;base64"), head
        raw = base64.b64decode(data)
        self._json(200, {"choices": [{"message": {"content": f"<think>x</think>Imagem de {len(raw)} bytes. Pedido: {prompt}"}}]})
