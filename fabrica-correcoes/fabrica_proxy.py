#!/usr/bin/env python3
"""Proxy de correção entre a Fábrica App (terminal 3.4.3) e o Ollama.

Corrige, sem mexer no executável da Fábrica:
  1. Ferramenta escrita como TEXTO (ex.: qwen2.5-coder) -> vira tool_call de verdade.
  2. "Sucesso" falso: a IA diz que criou/alterou arquivos sem chamar nenhuma
     ferramenta de escrita -> o proxy cobra a IA e, se ela insistir, avisa na tela.
  3. Loop: a mesma ação repetida várias vezes ou etapas demais -> o proxy para.
  4. Falha silenciosa: mantém a conexão viva enquanto o modelo carrega e, se o
     Ollama der erro, mostra a mensagem em vez de terminar com "0 tokens".

Só usa a biblioteca padrão do Python (3.8+).

Uso:
  python3 fabrica_proxy.py            # escuta em 127.0.0.1:11435
  fabrica --url http://127.0.0.1:11435/v1 -m qwen3:8b
"""

import argparse
import json
import re
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CONFIG = {
    "upstream": "http://127.0.0.1:11434",
    "timeout": 900,          # segundos esperando o Ollama
    "max_repeat": 2,         # mesma ação idêntica permitida até N vezes
    "max_steps": 30,         # máximo de ferramentas por pedido do usuário
    "retries": 2,            # quantas vezes cobrar a IA que mentiu
    "keepalive": 10,         # segundos entre sinais de vida no streaming
    "log": None,
}

WRITE_TOOL_RE = re.compile(
    r"write|edit|create|replace|patch|apply|append|insert|delete|remove|move|rename|mkdir|run|exec|command|shell",
    re.I)
CLAIM_RE = re.compile(
    r"(✓|✅|\bcriad[oa]s?\b|\bcriei\b|\bescrit[oa]s?\b|\bsalv[oa]s?\b|\balterad[oa]s?\b|"
    r"\batualizad[oa]s?\b|\bmodificad[oa]s?\b|\brodad[oa]s?\b|\bexecutad[oa]s?\b|\bpassaram\b|"
    r"\bcreated\b|\bwrote\b|\bwritten\b|\bsaved\b|\bupdated\b)", re.I)
FILENAME_RE = re.compile(r"[\w./-]+\.[A-Za-z0-9]{1,6}\b")
THINK_RE = re.compile(r"<think>.*?</think>", re.S)


def log(msg):
    line = time.strftime("%H:%M:%S ") + msg
    print(line, file=sys.stderr, flush=True)
    if CONFIG["log"]:
        with open(CONFIG["log"], "a", encoding="utf-8") as f:
            f.write(line + "\n")


# ---------------------------------------------------------------- correções

def tool_names(body):
    names = []
    for t in body.get("tools") or []:
        fn = t.get("function") or {}
        if fn.get("name"):
            names.append(fn["name"])
    return names


def extract_text_tool_calls(content, names):
    """Procura chamadas de ferramenta em JSON dentro do texto da resposta."""
    if not content or not names:
        return []
    text = THINK_RE.sub("", content)
    decoder = json.JSONDecoder()
    calls, pos = [], 0
    while True:
        start = text.find("{", pos)
        if start < 0:
            break
        try:
            obj, end = decoder.raw_decode(text, start)
        except ValueError:
            pos = start + 1
            continue
        pos = end
        objs = obj if isinstance(obj, list) else [obj]
        for o in objs:
            if not isinstance(o, dict):
                continue
            if isinstance(o.get("function"), dict):
                o = o["function"]
            name = o.get("name")
            args = o.get("arguments", o.get("parameters"))
            if name in names and args is not None:
                if not isinstance(args, str):
                    args = json.dumps(args, ensure_ascii=False)
                calls.append({
                    "id": "call_" + uuid.uuid4().hex[:8],
                    "type": "function",
                    "function": {"name": name, "arguments": args},
                })
    return calls


def turn_history(messages):
    """Ferramentas chamadas desde a última mensagem real do usuário."""
    last_user = 0
    for i, m in enumerate(messages):
        if m.get("role") == "user":
            last_user = i
    calls = []
    for m in messages[last_user:]:
        if m.get("role") == "assistant":
            for tc in m.get("tool_calls") or []:
                fn = tc.get("function") or {}
                calls.append((fn.get("name"), fn.get("arguments")))
    return calls


def signature(name, args):
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except ValueError:
            pass
    return name + "|" + json.dumps(args, sort_keys=True, ensure_ascii=False)


def claims_work(content):
    for line in (content or "").splitlines():
        if CLAIM_RE.search(line) and FILENAME_RE.search(line):
            return True
    return False


def call_upstream(body):
    """Pede ao Ollama em streaming (para registrar o progresso) e monta a resposta completa."""
    body = dict(body, stream=True, stream_options={"include_usage": True})
    req = urllib.request.Request(
        CONFIG["upstream"] + "/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"})
    t0 = time.time()
    last_log = t0
    first = None
    resp = {"id": None, "created": None, "model": body.get("model"), "usage": None}
    content, reasoning, calls, finish = [], [], {}, None
    with urllib.request.urlopen(req, timeout=CONFIG["timeout"]) as r:
        for raw in r:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            chunk = json.loads(data)
            if first is None:
                first = time.time()
                log("Ollama começou a responder após %.0fs" % (first - t0))
            resp["id"] = resp["id"] or chunk.get("id")
            resp["created"] = resp["created"] or chunk.get("created")
            if chunk.get("usage"):
                resp["usage"] = chunk["usage"]
            for ch in chunk.get("choices") or []:
                d = ch.get("delta") or {}
                if d.get("content"):
                    content.append(d["content"])
                if d.get("reasoning"):
                    reasoning.append(d["reasoning"])
                for tc in d.get("tool_calls") or []:
                    i = tc.get("index", len(calls))
                    cur = calls.setdefault(i, {"id": None, "type": "function",
                                               "function": {"name": "", "arguments": ""}})
                    cur["id"] = cur["id"] or tc.get("id")
                    fn = tc.get("function") or {}
                    cur["function"]["name"] += fn.get("name") or ""
                    cur["function"]["arguments"] += fn.get("arguments") or ""
                finish = ch.get("finish_reason") or finish
            if time.time() - last_log >= 15:
                last_log = time.time()
                log("  ... gerando há %.0fs: pensamento=%d car., texto=%d car., ferramentas=%d"
                    % (last_log - t0, len("".join(reasoning)), len("".join(content)), len(calls)))
    if first is None:
        raise RuntimeError("o Ollama encerrou sem enviar resposta (após %.0fs)" % (time.time() - t0))
    msg = {"role": "assistant", "content": "".join(content)}
    if reasoning:
        msg["reasoning"] = "".join(reasoning)
    if calls:
        msg["tool_calls"] = [calls[i] for i in sorted(calls)]
    log("Ollama terminou em %.0fs: texto=%d car., ferramentas=%s"
        % (time.time() - t0, len(msg["content"]),
           ", ".join(c["function"]["name"] for c in msg.get("tool_calls", [])) or "nenhuma"))
    resp.update(object="chat.completion", choices=[{
        "index": 0, "message": msg,
        "finish_reason": finish or ("tool_calls" if calls else "stop")}])
    return resp


def convert_text_calls(names, resp):
    """Correção 1: ferramenta escrita como texto vira tool_call de verdade."""
    if not resp.get("choices"):
        return resp
    choice = resp["choices"][0]
    msg = choice.setdefault("message", {})
    if not msg.get("tool_calls"):
        calls = extract_text_tool_calls(msg.get("content"), names)
        if calls:
            log("correção 1: %d ferramenta(s) em texto convertida(s): %s"
                % (len(calls), ", ".join(c["function"]["name"] for c in calls)))
            msg["tool_calls"] = calls
            msg["content"] = ""
            choice["finish_reason"] = "tool_calls"
    return resp


def fix_response(body, resp):
    """Aplica as correções 1, 2 e 3 numa resposta completa do Ollama."""
    names = tool_names(body)
    if not names or not resp.get("choices"):
        return resp
    resp = convert_text_calls(names, resp)
    choice = resp["choices"][0]
    msg = choice["message"]

    history = turn_history(body.get("messages") or [])
    write_names = [n for n in names if WRITE_TOOL_RE.search(n)]

    # 2. sucesso falso
    if not msg.get("tool_calls") and write_names:
        did_write = any(n in write_names for n, _ in history)
        tries = 0
        while not did_write and claims_work(msg.get("content")) and tries < CONFIG["retries"]:
            tries += 1
            log("correção 2: IA afirmou ter feito algo sem usar ferramentas; cobrando (tentativa %d)" % tries)
            retry = dict(body)
            retry["messages"] = list(body.get("messages") or []) + [
                {"role": "assistant", "content": msg.get("content") or ""},
                {"role": "user", "content":
                    "ATENÇÃO: você afirmou ter criado/alterado/rodado algo, mas NENHUMA ferramenta "
                    "foi chamada e NADA mudou no disco. Não descreva o trabalho: chame agora as "
                    "ferramentas (%s) para fazer de verdade." % ", ".join(write_names)},
            ]
            new = convert_text_calls(names, call_upstream(retry))
            if not new.get("choices"):
                break
            resp, choice = new, new["choices"][0]
            msg = choice.setdefault("message", {})
            if msg.get("tool_calls"):
                log("correção 2: a IA passou a usar ferramentas")
                break
        if not msg.get("tool_calls") and not did_write and claims_work(msg.get("content")):
            log("correção 2: IA insistiu na mentira; avisando o usuário")
            msg["content"] = ("⚠️ [proxy] A IA disse que concluiu, mas NENHUMA ferramenta de escrita "
                              "ou comando foi usado: nada foi alterado no disco.\n\n"
                              "Resposta original da IA:\n" + (msg.get("content") or ""))

    # 3. proteção contra loop
    if msg.get("tool_calls"):
        seen = {}
        for n, a in history:
            s = signature(n, a)
            seen[s] = seen.get(s, 0) + 1
        reason = None
        if len(history) + len(msg["tool_calls"]) > CONFIG["max_steps"]:
            reason = "mais de %d ações neste pedido" % CONFIG["max_steps"]
        for tc in msg["tool_calls"]:
            fn = tc.get("function") or {}
            if seen.get(signature(fn.get("name"), fn.get("arguments")), 0) >= CONFIG["max_repeat"]:
                reason = "a ação '%s' com os mesmos argumentos já foi repetida %d vezes" % (
                    fn.get("name"), CONFIG["max_repeat"])
        if reason:
            log("correção 3: loop detectado (%s); interrompendo" % reason)
            msg.pop("tool_calls", None)
            msg["content"] = ("⛔ [proxy] Proteção contra loop: %s. Parei para não repetir "
                              "indefinidamente. Revise o resultado e faça um pedido mais específico." % reason)
            choice["finish_reason"] = "stop"
    return resp


# ---------------------------------------------------------------- streaming

def sse_chunks(resp, include_usage):
    rid = resp.get("id") or "chatcmpl-proxy"
    created = resp.get("created") or int(time.time())
    model = resp.get("model") or ""
    choice = (resp.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    delta = {"role": "assistant", "content": msg.get("content") or ""}
    if msg.get("reasoning"):
        delta["reasoning"] = msg["reasoning"]
    if msg.get("tool_calls"):
        delta["tool_calls"] = [dict(tc, index=i) for i, tc in enumerate(msg["tool_calls"])]
    base = {"id": rid, "object": "chat.completion.chunk", "created": created, "model": model}
    yield dict(base, choices=[{"index": 0, "delta": delta, "finish_reason": None}])
    yield dict(base, choices=[{"index": 0, "delta": {},
                               "finish_reason": choice.get("finish_reason") or "stop"}])
    if include_usage and resp.get("usage"):
        yield dict(base, choices=[], usage=resp["usage"])


def error_response(body, err):
    return {
        "id": "chatcmpl-proxy-erro", "object": "chat.completion", "created": int(time.time()),
        "model": body.get("model", ""),
        "choices": [{"index": 0, "finish_reason": "stop", "message": {
            "role": "assistant",
            "content": "⚠️ [proxy] Erro ao falar com o Ollama: %s\n"
                       "Verifique se o Ollama está rodando (ollama ps) e se há memória livre (free -h)." % err}}],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


# ---------------------------------------------------------------- servidor

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _passthrough(self):
        length = int(self.headers.get("Content-Length") or 0)
        data = self.rfile.read(length) if length else None
        headers = {k: v for k, v in self.headers.items()
                   if k.lower() not in ("host", "content-length", "connection", "accept-encoding")}
        req = urllib.request.Request(CONFIG["upstream"] + self.path, data=data,
                                     headers=headers, method=self.command)
        try:
            with urllib.request.urlopen(req, timeout=CONFIG["timeout"]) as r:
                status, rheaders, out = r.status, r.headers, r.read()
        except urllib.error.HTTPError as e:
            status, rheaders, out = e.code, e.headers, e.read()
        except Exception as e:
            status, rheaders = 502, {}
            out = json.dumps({"error": {"message": "proxy: %s" % e}}).encode()
        self.send_response(status)
        self.send_header("Content-Type", rheaders.get("Content-Type", "application/json"))
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def do_GET(self):
        self._passthrough()

    def do_POST(self):
        if not self.path.rstrip("/").endswith("/chat/completions"):
            return self._passthrough()
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        stream = bool(body.get("stream"))
        include_usage = bool((body.get("stream_options") or {}).get("include_usage"))
        log("pedido: modelo=%s mensagens=%d ferramentas=%d stream=%s" % (
            body.get("model"), len(body.get("messages") or []), len(tool_names(body)), stream))

        result = {}

        def work():
            try:
                result["resp"] = fix_response(body, call_upstream(body))
            except Exception as e:  # noqa: BLE001 — qualquer falha vira mensagem visível
                log("erro no Ollama: %s" % e)
                result["resp"] = error_response(body, e)

        t = threading.Thread(target=work, daemon=True)
        t.start()

        if not stream:
            t.join()
            out = json.dumps(result["resp"], ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        try:
            while t.is_alive():
                t.join(CONFIG["keepalive"])
                if t.is_alive():
                    self.wfile.write(b": aguardando o modelo\n\n")
                    self.wfile.flush()
            for chunk in sse_chunks(result["resp"], include_usage):
                self.wfile.write(b"data: " + json.dumps(chunk, ensure_ascii=False).encode() + b"\n\n")
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            log("a Fábrica fechou a conexão antes da resposta")


def main():
    p = argparse.ArgumentParser(description="Proxy de correção Fábrica ↔ Ollama")
    p.add_argument("--porta", type=int, default=11435)
    p.add_argument("--ollama", default=CONFIG["upstream"], help="endereço do Ollama")
    p.add_argument("--max-repeticoes", type=int, default=CONFIG["max_repeat"])
    p.add_argument("--max-etapas", type=int, default=CONFIG["max_steps"])
    p.add_argument("--log", help="arquivo para gravar o registro das correções")
    a = p.parse_args()
    CONFIG.update(upstream=a.ollama.rstrip("/"), max_repeat=a.max_repeticoes,
                  max_steps=a.max_etapas, log=a.log)
    srv = ThreadingHTTPServer(("127.0.0.1", a.porta), Handler)
    log("proxy de correção ouvindo em http://127.0.0.1:%d/v1 -> %s" % (a.porta, CONFIG["upstream"]))
    log("use: fabrica --url http://127.0.0.1:%d/v1 -m qwen3:8b" % a.porta)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
