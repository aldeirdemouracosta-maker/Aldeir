"""Regressões das correções da auditoria."""
import subprocess
import sys

import pytest

from app.config import Settings
from app.core.resources import ResourceMonitor
from app.main import build_orchestrator, create_app
from app.core.router import ActionRouter
from app.core.registry import AgentRegistry
from app.terminal.processes import LimitedProcess
from tests.helpers import client as make_client


class P:
    name = "p"
    async def generate(self, m, p, system=None): return "r"
    async def list_models(self): return ["qwen2.5:0.5b", "qwen2.5-coder:0.5b"]


@pytest.fixture
def c(tmp_path):
    return make_client(create_app(Settings(state_path=tmp_path / "s.db"), provider=P(),
                                  monitor=ResourceMonitor(gpu_query=lambda: "")))


def test_testserver_host_is_not_accepted_in_production_config(tmp_path):
    from fastapi.testclient import TestClient
    app = create_app(Settings(state_path=tmp_path / "s.db"), provider=P())
    assert TestClient(app).get("/health").status_code == 400          # Host: testserver
    assert make_client(app).get("/health").status_code == 200


def test_origin_must_match_host_including_port(c):
    same = {"origin": "http://127.0.0.1:8000"}
    assert c.post("/management/agents/coder/disable", headers=same).status_code == 200
    other_port = {"origin": "http://127.0.0.1:9999"}      # outro app local em outra porta
    assert c.post("/management/agents/coder/enable", headers=other_port).status_code == 403
    assert c.get("/resources", headers=other_port).status_code == 403
    assert c.post("/management/agents/coder/enable",
                  headers={"origin": "https://127.0.0.1:8000"}).status_code == 403   # esquema diferente


def test_oversized_body_is_rejected(c):
    big = {"action": "chat", "payload": {"text": "x" * 1_100_000}}
    assert c.post("/run", json=big).status_code == 413


def test_interrupt_kills_child_process(tmp_path, monkeypatch):
    lp = LimitedProcess([sys.executable, "-c", "import time; time.sleep(60)"], tmp_path, timeout=30)
    real_wait = subprocess.Popen.wait
    calls = {"n": 0}

    def wait(self, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise KeyboardInterrupt
        return real_wait(self, timeout)
    monkeypatch.setattr(subprocess.Popen, "wait", wait)
    with pytest.raises(KeyboardInterrupt):
        lp.run()
    assert lp._proc.wait(timeout=5) is not None            # morreu, não ficou órfão


def test_coordinator_lease_outlives_job_timeout(tmp_path):
    s = Settings(job_timeout=300, coord_dir=tmp_path / "c")
    orch = build_orchestrator(s, ActionRouter(AgentRegistry()))
    assert orch.coordinator.ttl > s.job_timeout
    assert orch.snapshot()["coordination"] == {"capacity": 1, "in_use": 0}
