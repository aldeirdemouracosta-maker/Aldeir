import asyncio

import httpx
import pytest
from tests.helpers import client as TestClient

from app.agents.base import Agent
from app.agents.chat import ChatAgent
from app.agents.coder import CoderAgent
from app.config import Settings
from app.core.models import ProviderError, RegistryError, RouteError
from app.core.registry import AgentRegistry
from app.core.router import ActionRouter
from app.main import create_app
from app.providers.local_compatible import LocalCompatibleProvider
from app.providers.ollama import OllamaProvider


class FakeProvider:
    name = "fake"

    def __init__(self, models=("m",)):
        self.models, self.calls = list(models), []

    async def generate(self, model, prompt, system=None):
        self.calls.append((model, prompt, system))
        return f"eco:{prompt}"

    async def list_models(self):
        return self.models


class Dummy(Agent):
    def __init__(self, name, actions):
        self.name, self.actions = name, actions

    async def run(self, action, payload):
        return "x"


def run(coro):
    return asyncio.run(coro)


# --- Registry / Router ---
def test_registry_rejects_bad_name_and_duplicates():
    r = AgentRegistry()
    r.register(Dummy("alpha", ("a1",)))
    with pytest.raises(RegistryError):
        r.register(Dummy("Bad Name", ("b1",)))
    with pytest.raises(RegistryError):
        r.register(Dummy("alpha", ("zz",)))        # nome duplicado
    with pytest.raises(RegistryError):
        r.register(Dummy("beta", ("a1",)))         # ação duplicada
    with pytest.raises(RegistryError):
        r.register(Dummy("gamma", ()))             # sem ações


def test_router_is_deterministic_and_rejects_unknown():
    r = AgentRegistry()
    r.register(Dummy("alpha", ("a1", "a2")))
    router = ActionRouter(r)
    assert router.route("a2").name == "alpha"
    with pytest.raises(RouteError):
        router.route("nada")


def test_unregister_frees_actions():
    r = AgentRegistry()
    r.register(Dummy("alpha", ("a1",)))
    r.unregister("alpha")
    r.register(Dummy("beta", ("a1",)))
    assert r.owner_of("a1") == "beta"


# --- Agentes ---
def test_chat_actions_use_expected_prompts():
    p = FakeProvider()
    a = ChatAgent(p, "m")
    run(a.run("summarize", {"text": "oi"}))
    run(a.run("translate", {"text": "hi", "target": "francês"}))
    assert "Resuma" in p.calls[0][2]
    assert "francês" in p.calls[1][2]


def test_agents_require_text():
    with pytest.raises(ValueError):
        run(ChatAgent(FakeProvider(), "m").run("chat", {}))


def test_coder_never_touches_files(tmp_path):
    f = tmp_path / "a.py"
    f.write_text("x=1")
    run(CoderAgent(FakeProvider(), "m").run("code_propose", {"text": "mude x", "path": str(f)}))
    assert f.read_text() == "x=1"


def test_availability_reports_missing_model():
    ok, why = run(ChatAgent(FakeProvider(models=["outro"]), "m").available())
    assert not ok and "não instalado" in why


# --- Provedores com transporte simulado ---
def _client(handler, base="http://x"):
    return httpx.AsyncClient(base_url=base, transport=httpx.MockTransport(handler))


def test_ollama_generate_and_list():
    def h(req):
        if req.url.path == "/api/generate":
            return httpx.Response(200, json={"response": "ola"})
        return httpx.Response(200, json={"models": [{"name": "b"}, {"name": "a"}]})
    p = OllamaProvider("http://x", client=_client(h))
    assert run(p.generate("m", "p")) == "ola"
    assert run(p.list_models()) == ["a", "b"]


def test_ollama_errors_become_provider_error():
    p = OllamaProvider("http://x", client=_client(lambda r: httpx.Response(500, text="boom")))
    with pytest.raises(ProviderError):
        run(p.generate("m", "p"))

    def down(req):
        raise httpx.ConnectError("recusado")
    with pytest.raises(ProviderError):
        run(OllamaProvider("http://x", client=_client(down)).list_models())


def test_local_compatible_roundtrip():
    def h(req):
        if req.url.path == "/v1/chat/completions":
            return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})
        return httpx.Response(200, json={"data": [{"id": "z"}]})
    p = LocalCompatibleProvider("http://x", client=_client(h))
    assert run(p.generate("m", "p", system="s")) == "ok"
    assert run(p.list_models()) == ["z"]


# --- API ---
@pytest.fixture
def client():
    return TestClient(create_app(Settings(), provider=FakeProvider(models=["qwen2.5:0.5b"])))


def test_api_health_agents_run(client):
    assert client.get("/health").json()["agents"] == 6
    names = {a["name"]: a for a in client.get("/agents").json()}
    assert set(names) == {"chat", "coder", "vision", "speech", "voice", "rag"}
    assert names["chat"]["available"] is True
    assert names["coder"]["available"] is False  # modelo coder não instalado no fake
    r = client.post("/run", json={"action": "chat", "payload": {"text": "oi"}})
    assert r.status_code == 200 and r.json()["output"] == "eco:oi"


def test_api_errors(client):
    assert client.post("/run", json={"action": "x", "payload": {}}).status_code == 404
    assert client.post("/run", json={"action": "chat", "payload": {}}).status_code == 422


def test_api_rejects_foreign_host(client):
    assert client.get("/health", headers={"host": "evil.example"}).status_code == 400
