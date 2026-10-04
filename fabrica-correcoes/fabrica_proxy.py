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
import collections
import itertools
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
    "no_think": False,    # qwen3: pede resposta sem a etapa de raciocínio
}

WRITE_TOOL_RE = re.compile(
    r"write|edit|create|replace|patch|apply|append|insert|delete|remove|move|rename|mkdir|run|exec|command|shell",
    re.I)
PROMISE_RE = re.compile(
    r"\b(vou|irei|vamos|começarei|comecarei|iniciarei|farei|analisarei|verificarei|"
    r"let me|i will|i'll|i am going to|i'm going to)\b", re.I)
OFFER_RE = re.compile(r"\b(se (você )?quiser|se preferir|deseja|quer que|posso|would you like|if you want)\b", re.I)
ANALYSIS_RE = re.compile(
    r"\b(analis[ae]r?|anális[ea]|verifi(que|car)|revis[ae]r?|examin[ae]r?|investig(ue|ar)|"
    r"leia|ler|liste|listar|mostr[ae]r?|procur[ae]r?|encontr[ae]r?|analyze|review|check|inspect|find|list)\b", re.I)
CLAIM_RE = re.compile(
    r"(✓|✅|\bcriad[oa]s?\b|\bcriei\b|\bescrit[oa]s?\b|\bsalv[oa]s?\b|\balterad[oa]s?\b|"
    r"\batualizad[oa]s?\b|\bmodificad[oa]s?\b|\brodad[oa]s?\b|\bexecutad[oa]s?\b|\bpassaram\b|"
    r"\bcreated\b|\bwrote\b|\bwritten\b|\bsaved\b|\bupdated\b)", re.I)
FILENAME_RE = re.compile(r"[\w./-]+\.[A-Za-z][A-Za-z0-9]{0,5}\b")
THINK_RE = re.compile(r"<think>.*?</think>", re.S)
ACTION_RE = re.compile(
    r"\b(cri[ae]r?|escrev[ae]r?|alter[ae]r?|modifi(que|car)|corrij[ae]|corrigir|rod[ae]r?|execut[ae]r?|"
    r"implement[ae]r?|adicion[ae]r?|ger[ae]r?|fa[çc]a|fazer|atualiz[ae]r?|apag[ae]r?|remov[ae]r?|"
    r"instal[ae]r?|teste|testar|create|write|edit|fix|run|add|implement|update|delete|make|build)\b", re.I)
MAX_TEXT_AROUND_CALL = 300   # texto além do JSON para ainda considerar "chamada em texto"


# ---------------------------------------------------------------- atividade
# O que a página /atividade mostra: eventos recentes e pedidos em andamento.
ACT_LOCK = threading.Lock()
EVENTS = collections.deque(maxlen=400)
ACTIVE = {}
CURRENT = threading.local()      # status do pedido tratado nesta thread
_event_ids = itertools.count(1)
_request_ids = itertools.count(1)


def event(kind, text):
    with ACT_LOCK:
        EVENTS.append({"id": next(_event_ids), "hora": time.strftime("%H:%M:%S"),
                       "tipo": kind, "texto": text})


def set_status(**fields):
    st = getattr(CURRENT, "status", None)
    if st is not None:
        with ACT_LOCK:
            st.update(fields)


def short_args(args):
    """Resumo legível dos argumentos de uma ferramenta (caminho, comando...)."""
    try:
        a = json.loads(args) if isinstance(args, str) else args
    except ValueError:
        return str(args)[:100]
    if isinstance(a, dict):
        for k in ("path", "file", "file_path", "filename", "command", "cmd", "pattern", "query"):
            if a.get(k):
                return str(a[k])[:100]
        return ", ".join("%s=%s" % (k, str(v)[:40]) for k, v in list(a.items())[:3])
    return str(a)[:100]


def log(msg, kind="info"):
    if kind != "progresso":
        event(kind, msg)
    line = time.strftime("%H:%M:%S ") + msg
    if sys.stderr is not None:            # pythonw (Windows, sem janela) não tem console
        try:
            print(line, file=sys.stderr, flush=True)
        except UnicodeEncodeError:        # console do Windows sem UTF-8
            enc = sys.stderr.encoding or "ascii"
            print(line.encode(enc, "replace").decode(enc), file=sys.stderr, flush=True)
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
    calls, pos, used = [], 0, 0
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
        before = len(calls)
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
        if len(calls) > before:
            used += end - start
    # texto explicativo longo com um exemplo de JSON no meio não é uma chamada
    leftover = len(re.sub(r"```\w*|</?tool_call>|\s", "", text)) - used
    if calls and leftover > MAX_TEXT_AROUND_CALL:
        log("correção 1 ignorada: JSON de ferramenta no meio de %d car. de texto" % leftover, "correcao")
        return []
    return calls


def last_user_text(messages):
    for m in reversed(messages):
        if m.get("role") == "user" and isinstance(m.get("content"), str):
            return m["content"]
    return ""


def turn_history(messages):
    """Ferramentas chamadas desde a última mensagem real do usuário: (nome, args, resultado)."""
    last_user = 0
    for i, m in enumerate(messages):
        if m.get("role") == "user":
            last_user = i
    results = {m.get("tool_call_id"): str(m.get("content"))
               for m in messages[last_user:] if m.get("role") == "tool"}
    calls = []
    for m in messages[last_user:]:
        if m.get("role") == "assistant":
            for tc in m.get("tool_calls") or []:
                fn = tc.get("function") or {}
                calls.append((fn.get("name"), fn.get("arguments"), results.get(tc.get("id"))))
    return calls


def signature(name, args):
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except ValueError:
            pass
    return name + "|" + json.dumps(args, sort_keys=True, ensure_ascii=False)


def claims_work(content):
    for line in THINK_RE.sub("", content or "").splitlines():
        if CLAIM_RE.search(line) and FILENAME_RE.search(line):
            return True
    return False


def promises_next_step(content):
    """A resposta termina anunciando o que vai fazer (sem ter feito)?"""
    lines = [l.strip() for l in THINK_RE.sub("", content or "").splitlines() if l.strip()]
    if not lines:
        return False
    last = lines[-1]
    return bool(PROMISE_RE.search(last)) and not OFFER_RE.search(last) and not last.endswith("?")


def without_thinking(body):
    """qwen3: acrescenta /no_think à última mensagem do usuário (bem mais rápido em CPU)."""
    if not CONFIG["no_think"] or "qwen3" not in str(body.get("model", "")).lower():
        return body
    msgs = [dict(m) for m in body.get("messages") or []]
    for m in reversed(msgs):
        if m.get("role") == "user" and isinstance(m.get("content"), str):
            if "/no_think" not in m["content"]:
                m["content"] += "\n/no_think"
            break
    return dict(body, messages=msgs)


def call_upstream(body):
    """Pede ao Ollama em streaming (para registrar o progresso) e monta a resposta completa."""
    body = dict(without_thinking(body), stream=True, stream_options={"include_usage": True})
    req = urllib.request.Request(
        CONFIG["upstream"] + "/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"})
    t0 = time.time()
    last_log = t0
    first = None
    resp = {"id": None, "created": None, "model": body.get("model"), "usage": None}
    content, reasoning, calls, finish = [], [], {}, None
    clen = rlen = 0
    set_status(fase="aguardando o modelo", desde=t0, pensamento=0, texto=0, ferramentas=[])
    try:
        r = urllib.request.urlopen(req, timeout=CONFIG["timeout"])
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        raise RuntimeError("HTTP %d do servidor: %s" % (e.code, detail)) from None
    with r:
        for raw in r:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data)
            except ValueError:
                log("pedaço inválido ignorado: %s" % data[:120])
                continue
            if chunk.get("error"):
                err = chunk["error"]
                raise RuntimeError(err.get("message") if isinstance(err, dict) else str(err))
            if first is None:
                first = time.time()
                log("Ollama começou a responder após %.0fs" % (first - t0), "progresso")
                set_status(fase="gerando")
            resp["id"] = resp["id"] or chunk.get("id")
            resp["created"] = resp["created"] or chunk.get("created")
            if chunk.get("usage"):
                resp["usage"] = chunk["usage"]
            for ch in chunk.get("choices") or []:
                d = ch.get("delta") or {}
                if d.get("content"):
                    content.append(d["content"])
                    clen += len(d["content"])
                if d.get("reasoning") or d.get("reasoning_content"):
                    reasoning.append(d.get("reasoning") or d.get("reasoning_content"))
                    rlen += len(reasoning[-1])
                for tc in d.get("tool_calls") or []:
                    i = tc.get("index", len(calls))
                    cur = calls.setdefault(i, {"id": None, "type": "function",
                                               "function": {"name": "", "arguments": ""}})
                    cur["id"] = cur["id"] or tc.get("id")
                    fn = tc.get("function") or {}
                    cur["function"]["name"] += fn.get("name") or ""
                    cur["function"]["arguments"] += fn.get("arguments") or ""
                finish = ch.get("finish_reason") or finish
            set_status(pensamento=rlen, texto=clen,
                       ferramentas=[c["function"]["name"] for c in calls.values() if c["function"]["name"]])
            if time.time() - last_log >= 15:
                last_log = time.time()
                log("  ... gerando há %.0fs: pensamento=%d car., texto=%d car., ferramentas=%d"
                    % (last_log - t0, rlen, clen, len(calls)), "progresso")
    if first is None:
        raise RuntimeError("o Ollama encerrou sem enviar resposta (após %.0fs)" % (time.time() - t0))
    text = "".join(content)
    for t in THINK_RE.findall(text):          # servidores que deixam <think> no texto
        reasoning.append(t[7:-8])
    msg = {"role": "assistant", "content": THINK_RE.sub("", text).strip()}
    if reasoning:
        msg["reasoning"] = "".join(reasoning)
    if calls:
        msg["tool_calls"] = [calls[i] for i in sorted(calls)]
    set_status(fase="aplicando correções")
    log("Ollama terminou em %.0fs: texto=%d car., ferramentas=%s"
        % (time.time() - t0, len(msg["content"]),
           ", ".join(c["function"]["name"] for c in msg.get("tool_calls", [])) or "nenhuma"), "progresso")
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
                % (len(calls), ", ".join(c["function"]["name"] for c in calls)), "correcao")
            msg["tool_calls"] = calls
            msg["content"] = ""
            choice["finish_reason"] = "tool_calls"
    return resp


def fix_response(body, resp):
    """Aplica as correções 1 a 4 numa resposta completa do Ollama."""
    names = tool_names(body)
    if not names or not resp.get("choices"):
        return resp
    resp = convert_text_calls(names, resp)
    choice = resp["choices"][0]
    msg = choice["message"]

    messages = body.get("messages") or []
    history = turn_history(messages)
    write_names = [n for n in names if WRITE_TOOL_RE.search(n)]
    asked_action = bool(ACTION_RE.search(last_user_text(messages)))

    # 2. sucesso falso (só quando o usuário pediu para fazer algo)
    if not msg.get("tool_calls") and write_names and asked_action:
        did_write = any(n in write_names for n, _, _ in history)
        tries = 0
        while not did_write and claims_work(msg.get("content")) and tries < CONFIG["retries"]:
            tries += 1
            log("correção 2: IA afirmou ter feito algo sem usar ferramentas; cobrando (tentativa %d)" % tries, "correcao")
            retry = dict(body)
            retry["messages"] = list(body.get("messages") or []) + [
                {"role": "assistant", "content": msg.get("content") or ""},
                {"role": "user", "content":
                    "ATENÇÃO: você afirmou ter criado/alterado/rodado algo, mas NENHUMA ferramenta "
                    "foi chamada e NADA mudou no disco. Se o pedido exige criar, alterar ou rodar "
                    "algo, chame agora as ferramentas (%s) para fazer de verdade. Se não exige, "
                    "responda sem afirmar que alterou arquivos." % ", ".join(write_names)},
            ]
            new = convert_text_calls(names, call_upstream(retry))
            if not new.get("choices"):
                break
            resp, choice = new, new["choices"][0]
            msg = choice.setdefault("message", {})
            if msg.get("tool_calls"):
                log("correção 2: a IA passou a usar ferramentas", "correcao")
                break
        if not msg.get("tool_calls") and not did_write and tries and claims_work(msg.get("content")):
            log("correção 2: IA insistiu na mentira; avisando o usuário", "correcao")
            msg["content"] = ("⚠️ [proxy] A IA disse que concluiu, mas NENHUMA ferramenta de escrita "
                              "ou comando foi usado: nada foi alterado no disco.\n\n"
                              "Resposta original da IA:\n" + (msg.get("content") or ""))

    # 4. anunciou o próximo passo e parou (sem chamar ferramenta)
    asked_work = asked_action or bool(ANALYSIS_RE.search(last_user_text(messages)))
    if not msg.get("tool_calls") and asked_work and promises_next_step(msg.get("content")):
        tries = 0
        while tries < CONFIG["retries"] and promises_next_step(msg.get("content")):
            tries += 1
            log("correção 4: IA anunciou o próximo passo e parou; pedindo para executar (tentativa %d)"
                % tries, "correcao")
            retry = dict(body)
            retry["messages"] = list(messages) + [
                {"role": "assistant", "content": msg.get("content") or ""},
                {"role": "user", "content":
                    "Você anunciou o próximo passo, mas não o executou. Não descreva o plano: "
                    "comece agora, chamando as ferramentas necessárias (por exemplo: %s). "
                    "Se já tem tudo de que precisa, dê agora a resposta final completa."
                    % ", ".join(names[:8])},
            ]
            new = convert_text_calls(names, call_upstream(retry))
            if not new.get("choices"):
                break
            resp, choice = new, new["choices"][0]
            msg = choice.setdefault("message", {})
            if msg.get("tool_calls"):
                log("correção 4: a IA passou a executar", "correcao")
                break
        if not msg.get("tool_calls") and promises_next_step(msg.get("content")):
            msg["content"] = (msg.get("content") or "") + (
                "\n\n⚠️ [proxy] A IA anunciou o próximo passo mas parou. Envie \"continue\" para ela seguir.")

    # 3. proteção contra loop
    if msg.get("tool_calls"):
        outcomes = {}
        for n, a, res in history:
            outcomes.setdefault(signature(n, a), []).append(res)
        reason = None
        if len(history) + len(msg["tool_calls"]) > CONFIG["max_steps"]:
            reason = "mais de %d ações neste pedido" % CONFIG["max_steps"]
        for tc in msg["tool_calls"]:
            fn = tc.get("function") or {}
            past = outcomes.get(signature(fn.get("name"), fn.get("arguments")), [])
            # repetir um teste depois de mudar o código é normal; repetir com o mesmo resultado é loop
            if len(past) >= CONFIG["max_repeat"] and len(set(past)) == 1:
                reason = ("a ação '%s' já foi feita %d vezes com os mesmos argumentos e o mesmo "
                          "resultado" % (fn.get("name"), len(past)))
        if reason:
            log("correção 3: loop detectado (%s); interrompendo" % reason, "correcao")
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


# ---------------------------------------------------------------- página de atividade

def describe_incoming(messages):
    """Registra o que chegou da Fábrica: um pedido novo ou resultados de ferramentas."""
    if not messages:
        return
    last = messages[-1]
    if last.get("role") == "user":
        event("pedido", str(last.get("content") or "")[:400])
        return
    names = {}
    for m in reversed(messages):
        if m.get("role") == "assistant":
            for tc in m.get("tool_calls") or []:
                names[tc.get("id")] = (tc.get("function") or {}).get("name", "ferramenta")
            break
    for m in messages[::-1]:
        if m.get("role") != "tool":
            break
        out = " ".join(str(m.get("content") or "").split())
        event("resultado", "%s → %s" % (names.get(m.get("tool_call_id"), "ferramenta"), out[:200] or "(vazio)"))


def describe_outgoing(resp):
    msg = ((resp.get("choices") or [{}])[0]).get("message") or {}
    if msg.get("tool_calls"):
        for tc in msg["tool_calls"]:
            fn = tc.get("function") or {}
            event("ferramenta", "%s: %s" % (fn.get("name"), short_args(fn.get("arguments"))))
    else:
        event("resposta", " ".join(str(msg.get("content") or "").split())[:400] or "(resposta vazia)")


def activity_snapshot():
    now = time.time()
    with ACT_LOCK:
        ativos = [{"modelo": st.get("modelo"), "fase": st.get("fase"),
                   "segundos": round(now - st["inicio"]),
                   "fase_segundos": round(now - st.get("desde", st["inicio"])),
                   "pensamento": st.get("pensamento", 0), "texto": st.get("texto", 0),
                   "ferramentas": st.get("ferramentas", [])} for st in ACTIVE.values()]
        eventos = list(EVENTS)[-200:]
    return {"ativos": ativos, "eventos": eventos, "servidor": CONFIG["upstream"]}


ATIVIDADE_HTML = """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Atividade da Fábrica</title>
<style>
:root { --bg:#f6f7f9; --card:#fff; --tx:#1b1f24; --mut:#5b6573; --bd:#d9dee5;
  --azul:#1f6feb; --roxo:#8250df; --verde:#1a7f37; --ambar:#9a6700; --verm:#cf222e; }
@media (prefers-color-scheme: dark) { :root { --bg:#0d1117; --card:#161b22; --tx:#e6edf3;
  --mut:#9aa5b1; --bd:#30363d; --azul:#58a6ff; --roxo:#bc8cff; --verde:#3fb950; --ambar:#d29922; --verm:#ff7b72; } }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--tx); font:16px/1.5 system-ui, "Segoe UI", sans-serif; }
main { max-width:900px; margin:0 auto; padding:16px; }
h1 { font-size:1.3rem; margin:0 0 4px; }
.sub { color:var(--mut); font-size:.9rem; margin:0 0 16px; }
.card { background:var(--card); border:1px solid var(--bd); border-radius:10px; padding:14px 16px; margin-bottom:16px; }
#estado { font-size:1.15rem; font-weight:600; }
.det { color:var(--mut); margin-top:4px; }
.ponto { display:inline-block; width:12px; height:12px; border-radius:50%; margin-right:8px; background:var(--mut); }
.ocupado .ponto { background:var(--azul); animation:pulsa 1.2s infinite; }
@keyframes pulsa { 50% { opacity:.3; } }
@media (prefers-reduced-motion: reduce) { .ocupado .ponto { animation:none; } }
ol { list-style:none; margin:0; padding:0; }
li { display:grid; grid-template-columns:72px 110px 1fr; gap:8px; padding:8px 0; border-top:1px solid var(--bd); }
li:first-child { border-top:0; }
.hora { color:var(--mut); font-variant-numeric:tabular-nums; }
.tipo { font-weight:600; }
.texto { overflow-wrap:anywhere; white-space:pre-wrap; }
.t-pedido .tipo { color:var(--azul); } .t-ferramenta .tipo { color:var(--roxo); }
.t-resposta .tipo { color:var(--verde); } .t-correcao .tipo { color:var(--ambar); }
.t-erro .tipo, .t-erro .texto { color:var(--verm); } .t-resultado .tipo, .t-info .tipo { color:var(--mut); }
@media (max-width:560px) { li { grid-template-columns:1fr; gap:0; } }
</style></head><body><main>
<h1>Atividade da Fábrica</h1>
<p class="sub">Tudo o que passa entre o Fábrica App e a IA local. Atualiza sozinho a cada segundo.</p>
<section class="card" id="cartao" aria-live="polite">
  <div id="estado"><span class="ponto"></span>Conectando ao proxy…</div>
  <div class="det" id="detalhe"></div>
</section>
<section class="card"><ol id="eventos" aria-label="Eventos recentes, mais novos primeiro"></ol></section>
</main>
<script>
const NOMES = {pedido:"Pedido", ferramenta:"Ferramenta", resultado:"Resultado", resposta:"Resposta",
               correcao:"Correção", erro:"Erro", info:"Info"};
let ultimo = -1;
function esc(t) { const d = document.createElement("div"); d.textContent = t; return d.innerHTML; }
function fase(a) {
  let t = a.fase + " há " + a.fase_segundos + "s";
  if (a.fase === "gerando") {
    const p = [];
    if (a.pensamento) p.push(a.pensamento + " car. de raciocínio");
    if (a.texto) p.push(a.texto + " car. de texto");
    if (a.ferramentas.length) p.push("ferramenta: " + a.ferramentas.join(", "));
    if (p.length) t += " — " + p.join(", ");
  }
  return t;
}
async function atualiza() {
  try {
    const r = await fetch("atividade.json", {cache: "no-store"});
    const d = await r.json();
    const cartao = document.getElementById("cartao");
    if (d.ativos.length) {
      const a = d.ativos[0];
      cartao.className = "card ocupado";
      document.getElementById("estado").innerHTML = '<span class="ponto"></span>Trabalhando (' + esc(a.modelo || "") + ")";
      document.getElementById("detalhe").textContent = fase(a) + " · total " + a.segundos + "s";
    } else {
      cartao.className = "card";
      document.getElementById("estado").innerHTML = '<span class="ponto"></span>Ocioso: esperando um pedido';
      document.getElementById("detalhe").textContent = "Servidor de IA: " + d.servidor;
    }
    const topo = d.eventos.length ? d.eventos[d.eventos.length - 1].id : 0;
    if (topo !== ultimo) {
      ultimo = topo;
      document.getElementById("eventos").innerHTML = d.eventos.slice().reverse().map(e =>
        '<li class="t-' + e.tipo + '"><span class="hora">' + e.hora + '</span><span class="tipo">' +
        (NOMES[e.tipo] || e.tipo) + '</span><span class="texto">' + esc(e.texto) + "</span></li>").join("");
    }
  } catch (e) {
    document.getElementById("cartao").className = "card";
    document.getElementById("estado").innerHTML = '<span class="ponto"></span>Proxy desligado ou inacessível';
    document.getElementById("detalhe").textContent = "";
  }
}
atualiza(); setInterval(atualiza, 1000);
</script></body></html>
"""


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

    def _send(self, status, ctype, out):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(out)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(out)

    def do_GET(self):
        path = self.path.split("?")[0].rstrip("/")
        if path in ("", "/atividade"):
            return self._send(200, "text/html; charset=utf-8", ATIVIDADE_HTML.encode("utf-8"))
        if path == "/atividade.json":
            return self._send(200, "application/json; charset=utf-8",
                              json.dumps(activity_snapshot()).encode())
        self._passthrough()

    do_PUT = do_DELETE = do_GET

    def do_POST(self):
        if not self.path.rstrip("/").endswith("/chat/completions"):
            return self._passthrough()
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            out = b'{"error": {"message": "proxy: corpo JSON invalido"}}'
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)
            return
        stream = bool(body.get("stream"))
        include_usage = bool((body.get("stream_options") or {}).get("include_usage"))
        log("pedido: modelo=%s mensagens=%d ferramentas=%d stream=%s" % (
            body.get("model"), len(body.get("messages") or []), len(tool_names(body)), stream), "progresso")
        describe_incoming(body.get("messages") or [])
        rid = next(_request_ids)
        status = {"modelo": body.get("model"), "inicio": time.time(), "fase": "recebido"}
        with ACT_LOCK:
            ACTIVE[rid] = status

        result = {}

        def work():
            CURRENT.status = status
            try:
                result["resp"] = fix_response(body, call_upstream(body))
                describe_outgoing(result["resp"])
            except Exception as e:  # noqa: BLE001 — qualquer falha vira mensagem visível
                log("erro no Ollama: %s" % e, "erro")
                result["resp"] = error_response(body, e)
            finally:
                with ACT_LOCK:
                    ACTIVE.pop(rid, None)

        t = threading.Thread(target=work, daemon=True)
        t.start()

        if not stream:
            t.join()
            out = json.dumps(result["resp"]).encode()   # só ASCII: acentos viram \uXXXX
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
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
                self.wfile.write(b"data: " + json.dumps(chunk).encode() + b"\n\n")
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            log("a Fábrica fechou a conexão antes da resposta", "erro")


def main():
    p = argparse.ArgumentParser(description="Proxy de correção Fábrica ↔ Ollama")
    p.add_argument("--porta", type=int, default=11435)
    p.add_argument("--ollama", default=CONFIG["upstream"], help="endereço do Ollama")
    p.add_argument("--max-repeticoes", type=int, default=CONFIG["max_repeat"])
    p.add_argument("--max-etapas", type=int, default=CONFIG["max_steps"])
    p.add_argument("--log", help="arquivo para gravar o registro das correções")
    p.add_argument("--sem-pensar", action="store_true",
                   help="qwen3: desliga a etapa de raciocínio (/no_think); bem mais rápido sem GPU")
    a = p.parse_args()
    CONFIG.update(upstream=a.ollama.rstrip("/"), max_repeat=a.max_repeticoes,
                  max_steps=a.max_etapas, log=a.log, no_think=a.sem_pensar)
    srv = ThreadingHTTPServer(("127.0.0.1", a.porta), Handler)
    log("proxy de correção ouvindo em http://127.0.0.1:%d/v1 -> %s" % (a.porta, CONFIG["upstream"]))
    if CONFIG["no_think"]:
        log("modo sem raciocínio ativo para modelos qwen3 (/no_think)")
    log("use: fabrica --url http://127.0.0.1:%d/v1 -m qwen3:8b" % a.porta)
    log("acompanhe a atividade em: http://127.0.0.1:%d/atividade" % a.porta)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
