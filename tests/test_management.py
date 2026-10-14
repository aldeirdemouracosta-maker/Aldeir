import asyncio

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.core.manager import ManagerError
from app.core.resources import ResourceMonitor, parse_gpus
from app.core.state import StateStore
from app.main import build_manager, create_app
from app.providers.ollama import OllamaProvider
import httpx


class FakeProvider:
    name = "fake"

    def __init__(self, models=("qwen2.5:0.5b", "qwen2.5-coder:0.5b", "outro")):
        self.models = list(models)

    async def generate(self, model, prompt, system=None):
        return f"[{model}] {prompt}"

    async def list_models(self):
        return self.models

    async def loaded_models(self):
        return ["outro"]


def run(c):
    return asyncio.run(c)


# --- StateStore ---
def test_state_store_prefs_agents_events(tmp_path):
    db = tmp_path / "x" / "s.db"
    s = StateStore(db)
    s.set_pref("tema", {"escuro": True})
    s.set_agent_state("chat", {"enabled": False})
    s.log_event("a", {"n": 1}); s.log_event("b")
    s.close()
    s2 = StateStore(db)
    assert s2.get_pref("tema") == {"escuro": True} and s2.get_pref("nada", 7) == 7
    assert s2.agent_states() == {"chat": {"enabled": False}}
    assert [e["kind"] for e in s2.events()] == ["b", "a"]
    assert len(s2.events(limit=1)) == 1


# --- AgentManager ---
def mk(tmp_path, provider=None):
    return build_manager(Settings(state_path=tmp_path / "s.db"), provider or FakeProvider())


def test_manager_disable_enable_persist_across_restart(tmp_path):
    m = mk(tmp_path)
    assert m.registry.names() == ["chat", "coder"]
    m.disable("coder")
    assert m.registry.names() == ["chat"]
    m.store.close()
    m2 = mk(tmp_path)                      # "reinício": estado salvo prevalece sobre o YAML
    assert m2.registry.names() == ["chat"]
    m2.enable("coder")
    assert m2.registry.names() == ["chat", "coder"]
    m2.enable("coder")                     # idempotente
    assert [e["kind"] for e in m2.store.events()][:1] == ["agent.enabled"]


def test_manager_unknown_agent(tmp_path):
    m = mk(tmp_path)
    for fn in (m.enable, m.disable):
        with pytest.raises(ManagerError):
            fn("fantasma")


def test_set_model_validates_against_installed_and_persists(tmp_path):
    m = mk(tmp_path)
    run(m.set_model("chat", "outro"))
    assert m.registry.get("chat").model == "outro"
    with pytest.raises(ManagerError):
        run(m.set_model("chat", "nao-instalado"))
    with pytest.raises(ManagerError):
        run(m.set_model("chat", "  "))
    assert m.registry.get("chat").model == "outro"
    m.store.close()
    assert mk(tmp_path).registry.get("chat").model == "outro"


def test_set_model_provider_down_is_error_not_crash(tmp_path):
    def down(req):
        raise httpx.ConnectError("x")
    p = OllamaProvider("http://x", client=httpx.AsyncClient(base_url="http://x", transport=httpx.MockTransport(down)))
    m = mk(tmp_path, p)
    with pytest.raises(ManagerError):
        run(m.set_model("chat", "qualquer"))


# --- Recursos ---
def test_parse_gpus():
    assert parse_gpus("RTX 3060, 12288, 1024\n") == [
        {"name": "RTX 3060", "vram_total_mb": 12288, "vram_used_mb": 1024}]
    assert parse_gpus("lixo\n[N/A], [N/A], [N/A]") == []


def test_monitor_snapshot_real_values_and_no_gpu():
    def no_gpu():
        raise FileNotFoundError("nvidia-smi")
    snap = ResourceMonitor(gpu_query=no_gpu).snapshot()
    assert snap["gpus"] == [] and snap["ram_total_mb"] > 0
    assert 0 <= snap["cpu_percent"] <= 100
    assert snap["ram_used_mb"] <= snap["ram_total_mb"]


# --- API ---
@pytest.fixture
def client(tmp_path):
    app = create_app(Settings(state_path=tmp_path / "s.db"), provider=FakeProvider(),
                     monitor=ResourceMonitor(gpu_query=lambda: "GPU X, 8000, 100"))
    return TestClient(app)


def test_api_management_flow(client):
    a = {x["name"]: x for x in client.get("/management/agents").json()}
    assert a["chat"]["enabled"] and a["chat"]["available"]
    assert client.post("/management/agents/coder/disable").status_code == 200
    a = {x["name"]: x for x in client.get("/management/agents").json()}
    assert a["coder"]["enabled"] is False and a["coder"]["reason"] == "desativado"
    assert client.post("/run", json={"action": "code_review", "payload": {"text": "x"}}).status_code == 404
    assert client.post("/management/agents/coder/enable").status_code == 200
    assert client.put("/management/agents/chat/model", json={"model": "outro"}).status_code == 200
    assert client.put("/management/agents/chat/model", json={"model": "zzz"}).status_code == 409
    assert client.post("/management/agents/nada/enable").status_code == 404
    kinds = [e["kind"] for e in client.get("/management/events").json()]
    assert "agent.disabled" in kinds and "agent.model_changed" in kinds


def test_api_models_and_resources(client):
    m = client.get("/management/models").json()
    assert m["loaded"] == ["outro"] and "outro" in m["installed"]
    r = client.get("/resources").json()
    assert r["gpus"][0]["vram_total_mb"] == 8000 and r["ram_total_mb"] > 0


# --- Segurança de origem ---
def test_origin_and_fetch_metadata(client):
    ok = {"origin": "http://127.0.0.1:8000"}
    assert client.post("/management/agents/coder/disable", headers=ok).status_code == 200
    evil = {"origin": "http://evil.example"}
    assert client.post("/management/agents/coder/enable", headers=evil).status_code == 403
    assert client.get("/resources", headers=evil).status_code == 403
    assert client.post("/management/agents/coder/enable",
                       headers={"sec-fetch-site": "cross-site"}).status_code == 403
    assert client.get("/resources", headers={"sec-fetch-site": "cross-site"}).status_code == 403
    # mutação recusada não pode ter efeito
    names = {x["name"]: x for x in client.get("/management/agents").json()}
    assert names["coder"]["enabled"] is False
    assert client.get("/resources", headers={"sec-fetch-site": "same-origin"}).status_code == 200
    assert client.get("/health", headers={"host": "evil.example"}).status_code == 400
