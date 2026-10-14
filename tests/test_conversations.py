import asyncio

import pytest
from typer.testing import CliRunner

from app.agents.chat import ChatAgent
from app.config import Settings
from app.core.conversations import MAX_MESSAGE_CHARS, MAX_STORED, ConversationError, ConversationStore
from app.core.models import ProviderError
from app.main import create_app
from app.providers.local_compatible import LocalCompatibleProvider
from app.providers.ollama import OllamaProvider
from tests.fake_servers import CHAT, OllamaHandler, OpenAIHandler, Server
from tests.helpers import client as make_client


def run(c):
    return asyncio.run(c)


# ---------- ConversationStore ----------
def test_store_order_isolation_and_persistence(tmp_path):
    db = tmp_path / "x" / "c.db"
    s = ConversationStore(db)
    for i in range(3):
        s.add("a", "user", f"u{i}"); s.add("a", "assistant", f"r{i}")
    s.add("b", "user", "outra sessão")
    assert [m["content"] for m in s.history("a")] == ["u0", "r0", "u1", "r1", "u2", "r2"]
    assert s.history("b") == [{"role": "user", "content": "outra sessão"}]
    s.close()
    assert len(ConversationStore(db).history("a")) == 6                       # sobrevive a reinício


def test_store_limits_prune_and_caps():
    s = ConversationStore()
    for i in range(MAX_STORED + 15):
        s.add("a", "user", f"m{i}")
    h = s.history("a", max_messages=1000, max_chars=10**6)
    assert len(h) == MAX_STORED and h[-1]["content"] == f"m{MAX_STORED + 14}" and h[0]["content"] == "m15"
    assert [m["content"] for m in s.history("a", max_messages=3)] == [f"m{MAX_STORED + 12}", f"m{MAX_STORED + 13}", f"m{MAX_STORED + 14}"]
    s.add("c", "user", "x" * (MAX_MESSAGE_CHARS + 500))
    assert len(s.history("c")[0]["content"]) == MAX_MESSAGE_CHARS
    for _ in range(5):
        s.add("d", "user", "y" * 100)
    assert len(s.history("d", max_chars=250)) == 2                            # teto de caracteres respeitado
    assert len(s.history("d", max_chars=10)) == 1                             # nunca devolve vazio se há mensagem


def test_store_validates_session_and_role_and_clear():
    s = ConversationStore()
    for bad in ("", "a b", "../x", "a/b", "x" * 65, None, 5, "é"):
        with pytest.raises(ConversationError):
            s.history(bad)
        with pytest.raises(ConversationError):
            s.add(bad, "user", "x")
    with pytest.raises(ConversationError):
        s.add("a", "system", "x")
    s.add("a", "user", "1"); s.add("a", "user", "2")
    assert s.clear("a") == 2 and s.history("a") == [] and s.clear("a") == 0


# ---------- Agente + provedores reais por HTTP ----------
@pytest.mark.parametrize("handler,cls", [(OllamaHandler, OllamaProvider), (OpenAIHandler, LocalCompatibleProvider)])
def test_chat_remembers_across_turns_over_real_http(handler, cls):
    async def go():
        with Server(handler) as srv:
            p = cls(srv.url, timeout=5)
            agent = ChatAgent(p, CHAT, ConversationStore())
            assert await agent.run("chat", {"text": "Oi, meu nome é Ana", "session": "s1"}) == "ok"   # 1º turno: sem histórico
            assert await agent.run("chat", {"text": "Qual é o meu nome?", "session": "s1"}) == "Seu nome é Ana."
            assert "Ana" not in await agent.run("chat", {"text": "Qual é o meu nome?", "session": "s2"})   # outra sessão
            assert "Ana" not in await agent.run("chat", {"text": "Qual é o meu nome?"})                 # sem session: sem memória
            await p.aclose()
            return srv.requests
    reqs = run(go())
    paths = {r["path"] for r in reqs if r["method"] == "POST"}
    assert ("/api/chat" in paths) if handler is OllamaHandler else ("/v1/chat/completions" in paths)
    msgs = next(r for r in reqs if r["method"] == "POST" and "Qual" in str(r["body"]))["body"]["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]         # histórico + nova pergunta, em ordem


def test_failed_generation_does_not_pollute_memory():
    class Falha:
        name = "f"
        async def generate(self, *a, **k): raise ProviderError("caiu")
    store = ConversationStore()
    with pytest.raises(ProviderError):
        run(ChatAgent(Falha(), "m", store).run("chat", {"text": "oi", "session": "s"}))
    assert store.history("s") == []


def test_summarize_and_translate_ignore_session():
    seen = []

    class P:
        name = "p"
        async def generate(self, model, prompt, system=None, history=None):
            seen.append(history)
            return "ok"
    store = ConversationStore()
    a = ChatAgent(P(), "m", store)
    run(a.run("summarize", {"text": "x", "session": "s"}))
    assert seen == [None] and store.history("s") == []
    with pytest.raises(ConversationError):
        run(a.run("chat", {"text": "x", "session": "../etc"}))


# ---------- API ----------
class Memo:
    name = "memo"
    async def generate(self, model, prompt, system=None, history=None):
        return f"visto:{len(history or [])}"
    async def list_models(self): return ["qwen2.5:0.5b", "qwen2.5-coder:0.5b"]


def test_api_session_flow_and_clear(tmp_path):
    c = make_client(create_app(Settings(state_path=tmp_path / "s.db"), provider=Memo()))
    r1 = c.post("/run", json={"action": "chat", "payload": {"text": "a", "session": "ana"}}).json()["output"]
    r2 = c.post("/run", json={"action": "chat", "payload": {"text": "b", "session": "ana"}}).json()["output"]
    assert (r1, r2) == ("visto:0", "visto:2")
    assert [m["role"] for m in c.get("/sessions/ana").json()] == ["user", "assistant", "user", "assistant"]
    assert c.get("/sessions/outra").json() == []
    assert c.get("/sessions/a b").status_code in (404, 422)
    assert c.post("/run", json={"action": "chat", "payload": {"text": "x", "session": "../x"}}).status_code == 422
    assert c.delete("/sessions/ana", headers={"origin": "http://evil.example"}).status_code == 403
    assert c.get("/sessions/ana", headers={"origin": "http://evil.example", "sec-fetch-site": "cross-site"}).status_code == 403
    assert c.delete("/sessions/ana").json() == {"session": "ana", "deleted": 4}
    assert c.get("/sessions/ana").json() == []
    assert (tmp_path / "conversations.db").exists()                          # separado do estado dos agentes


# ---------- CLI ----------
def test_cli_chat_remembers_and_clear(tmp_path, monkeypatch):
    import app.cli.main as cm
    with Server(OllamaHandler) as srv:
        monkeypatch.setenv("SWARM_PROVIDER_URL", srv.url)
        monkeypatch.setenv("SWARM_STATE", str(tmp_path / "s.db"))
        monkeypatch.setenv("SWARM_MEDIA", str(tmp_path / "m"))
        monkeypatch.setenv("SWARM_CONVERSATIONS", str(tmp_path / "c.db"))
        r = CliRunner().invoke(cm.app, ["chat", "--session", "t"], input="Oi, meu nome é Bia\nQual é o meu nome?\n\n")
        assert r.exit_code == 0, r.output
        assert "Seu nome é Bia." in r.output
        r = CliRunner().invoke(cm.app, ["chat", "--session", "t"], input="Qual é o meu nome?\n\n")     # nova execução: memória persistiu
        assert "Seu nome é Bia." in r.output
        assert "6 mensagem(ns) apagada(s)" in CliRunner().invoke(cm.app, ["chat", "--session", "t", "--clear"]).output
        assert CliRunner().invoke(cm.app, ["chat", "--session", "../x", "--clear"]).exit_code == 1
