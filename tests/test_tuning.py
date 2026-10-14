import asyncio
from pathlib import Path

import pytest
from typer.testing import CliRunner

from app.config import Settings
from app.core.state import StateStore
from app.core.tuning import (MARGIN, SuiteError, check_output, evaluate, load_suite, recommend, record)
from app.main import build_manager, create_app
from tests.helpers import client as make_client

EVALS = Path(__file__).resolve().parent.parent / "evals"


def run(c):
    return asyncio.run(c)


# ---------- check_output ----------
def test_check_output_rules():
    assert check_output("Olá mundo", {"contains": ["MUNDO"], "max_chars": 20}) == (True, "")
    assert check_output("x", {"contains": ["y"]})[0] is False
    assert check_output("```py```", {"not_contains": ["```"]})[0] is False
    assert check_output("abc", {"regex": "^b"})[0] is False
    assert check_output("a" * 50, {"max_chars": 10})[1].startswith("50 caracteres")
    assert check_output('[{"a": 1}]', {"json": True})[0] and not check_output("não", {"json": True})[0]


# ---------- suítes reais do repositório ----------
def test_real_suites_are_valid_and_use_real_actions(tmp_path):
    m = build_manager(Settings(media_dir=tmp_path / "m"), provider=None)
    suites = sorted(EVALS.glob("*.yaml"))
    assert {p.stem for p in suites} >= {"chat", "coder", "langid", "planner"}
    for p in suites:
        suite = load_suite(p.stem, EVALS)
        agent = m.factories[p.stem]
        ids = [c["id"] for c in suite.cases]
        assert len(ids) == len(set(ids)), f"ids repetidos em {p.name}"
        assert {c["action"] for c in suite.cases} <= set(agent.actions), p.name


def test_suite_errors(tmp_path):
    with pytest.raises(SuiteError, match="sem suíte"):
        load_suite("nada", tmp_path)
    (tmp_path / "x.yaml").write_text("cases:\n  - {id: a, action: b}\n")
    with pytest.raises(SuiteError, match="inválido"):
        load_suite("x", tmp_path)


def test_suite_hash_changes_with_content(tmp_path):
    (tmp_path / "x.yaml").write_text("cases: []\n")
    a = load_suite("x", tmp_path).sha
    (tmp_path / "x.yaml").write_text("cases: []\n# mudou\n")
    assert load_suite("x", tmp_path).sha != a


# ---------- evaluate ----------
class Agent:
    def __init__(self, fn): self.fn = fn
    async def run(self, action, payload): return await self.fn(action, payload)


def suite_of(*cases):
    return type("S", (), {"agent": "a", "sha": "s1", "cases": list(cases)})()


def case(i, check, payload=None):
    return {"id": i, "action": "x", "payload": payload or {}, "check": check}


def test_evaluate_counts_failures_errors_and_timeouts():
    async def fn(action, payload):
        if payload.get("boom"):
            raise RuntimeError("modelo caiu")
        if payload.get("slow"):
            await asyncio.sleep(5)
        return "ok"
    s = suite_of(case("a", {"contains": ["ok"]}), case("b", {"contains": ["zzz"]}),
                 case("c", {}, {"boom": 1}), case("d", {}, {"slow": 1}))
    r = run(evaluate(Agent(fn), s, timeout=0.2))
    assert (r["passed"], r["total"]) == (1, 4)
    assert any("b: faltou" in f for f in r["fails"]) and any("c: erro: modelo caiu" in f for f in r["fails"])
    assert any(f.startswith("d: erro") for f in r["fails"])


# ---------- recommend ----------
def row(model, passed, total=10, ms=100):
    return {"model": model, "passed": passed, "total": total, "latency_ms": ms}


def test_recommend_policy():
    assert recommend([], "a").model is None
    assert recommend([row("a", 3), row("b", 4)], "a").model is None                  # ninguém chega a 50%
    assert recommend([row("a", 8), row("b", 8, ms=10)], "a").model is None           # empate: manter o atual
    assert recommend([row("a", 7), row("b", 7 + 0)], "a").model is None
    r = recommend([row("a", 6), row("b", 9)], "a")
    assert r.model == "b" and "atual a: 60%" in r.reason
    assert recommend([row("a", 6), row("b", 6.5)], "a").model is None and MARGIN == 0.1  # abaixo da margem
    assert recommend([row("a", 9, ms=500), row("b", 9, ms=50)], "x").model == "b"     # atual sem avaliação: desempate por latência


# ---------- StateStore ----------
def test_store_keeps_latest_eval_per_model_and_suite(tmp_path):
    st = StateStore(tmp_path / "s.db")
    s = suite_of()
    record(st, s, "m1", {"passed": 2, "total": 10, "latency_ms": 5})
    record(st, s, "m1", {"passed": 8, "total": 10, "latency_ms": 7})
    record(st, s, "m2", {"passed": 5, "total": 10, "latency_ms": 9})
    s.sha = "s2"
    record(st, s, "m1", {"passed": 1, "total": 10, "latency_ms": 1})
    assert st.latest_evals("a", "s1") == [row("m1", 8, ms=7), row("m2", 5, ms=9)]
    assert st.latest_evals("a", "s2") == [row("m1", 1, ms=1)]                     # suíte nova: histórico antigo não vale
    assert st.latest_evals("outro", "s1") == []


# ---------- CLI ponta a ponta (provedor simulado) ----------
class Smart:
    """'bom' acerta a suíte do chat; 'ruim' devolve vazio."""
    name = "smart"
    async def list_models(self): return ["bom", "ruim"]
    async def aclose(self): pass

    async def generate(self, model, prompt, system=None):
        if model == "ruim":
            return ""
        if system and "Resuma" in system:
            return "Lançamento em março."
        if system and "Traduza" in system:
            return "Good morning, how are you?"
        if "2 + 2" in prompt:
            return "4"
        return "Olá!"


@pytest.fixture
def cli(tmp_path, monkeypatch):
    import app.cli.main as cm
    monkeypatch.setenv("SWARM_STATE", str(tmp_path / "s.db"))
    monkeypatch.setenv("SWARM_MEDIA", str(tmp_path / "media"))
    monkeypatch.setattr(cm, "build_provider", lambda s: Smart())
    return cm, tmp_path


def invoke(cm, *args):
    return CliRunner().invoke(cm.app, list(args))


def test_tune_recommends_without_applying_then_applies(cli):
    cm, tmp = cli
    r = invoke(cm, "tune", "chat", "--evals-dir", str(EVALS))
    assert r.exit_code == 0, r.output
    assert "bom: 4/4" in r.output and "ruim: 0/4" in r.output
    assert "recomendação:" in r.output and "--apply" in r.output
    assert StateStore(tmp / "s.db").agent_states() == {}                     # nada foi trocado
    r = invoke(cm, "tune", "chat", "--models", "bom", "--apply", "--evals-dir", str(EVALS))
    assert "trocado para bom" in r.output
    assert StateStore(tmp / "s.db").agent_states()["chat"]["model"] == "bom"


def test_tune_errors_are_clean(cli):
    cm, _ = cli
    r = invoke(cm, "tune", "fantasma", "--evals-dir", str(EVALS))
    assert r.exit_code == 1 and "desconhecido" in r.output
    r = invoke(cm, "tune", "voice", "--evals-dir", str(EVALS))
    assert r.exit_code == 1 and "sem suíte" in r.output
    r = invoke(cm, "tune", "chat", "--models", "inexistente,bom", "--evals-dir", str(EVALS))
    assert "ignorado (não instalado): inexistente" in r.output and "bom: 4/4" in r.output


def test_tune_model_free_agent_measures_real_implementation(cli):
    cm, _ = cli
    r = invoke(cm, "tune", "langid", "--evals-dir", str(EVALS))
    assert r.exit_code == 0 and "langid: 19/19" in r.output


# ---------- feedback via API ----------
class P:
    name = "p"
    async def generate(self, m, p, system=None): return "r"
    async def list_models(self): return ["qwen2.5:0.5b", "qwen2.5-coder:0.5b"]


def test_feedback_api(tmp_path):
    c = make_client(create_app(Settings(state_path=tmp_path / "s.db"), provider=P()))
    jid = c.post("/run", json={"action": "chat", "payload": {"text": "oi"}}).json()["job_id"]
    assert c.post("/feedback", json={"job_id": jid, "rating": 1}).status_code == 200
    assert c.post("/feedback", json={"job_id": jid, "rating": -1}).status_code == 200
    assert c.post("/feedback", json={"job_id": jid, "rating": 5}).status_code == 422
    assert c.post("/feedback", json={"job_id": "job-999", "rating": 1}).status_code == 404
    assert c.post("/feedback", json={"job_id": jid, "rating": 1}, headers={"origin": "http://evil.example"}).status_code == 403
    s = c.get("/management/feedback").json()
    assert s == [{"agent": "chat", "model": "qwen2.5:0.5b", "up": 1, "down": 1}]
    bad = c.post("/run", json={"action": "chat", "payload": {}})                # job com erro não recebe feedback
    assert bad.status_code == 422
