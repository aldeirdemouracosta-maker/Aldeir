import asyncio
import json
import os
import threading
import time

import pytest
from tests.helpers import client as TestClient

from app.agents.base import Agent
from app.config import Settings
from app.core.coordination import ResourceCoordinator
from app.core.locking import FileLock, LockTimeout, try_create
from app.core.memory import MemoryManager
from app.core.orchestrator import JobCancelled, JobTimeout, Orchestrator
from app.core.registry import AgentRegistry
from app.core.router import ActionRouter
from app.core.scheduler import HIGH, LOW, NORMAL, AdmissionError, Job, QueueFull, ResourceScheduler
from app.main import create_app
from app.terminal.patches import PatchManager
from app.terminal.workspace import Workspace


def mem(avail=4000, total=8000, headroom=0, est=None):
    return MemoryManager(headroom, est, available=lambda: avail, total=lambda: total)


class Slow(Agent):
    """Agente de teste: registra a ordem e a concorrência real."""
    description = ""

    def __init__(self, name, action, delay=0.05, fail=False):
        self.name, self.actions, self.delay, self.fail = name, (action,), delay, fail
        self.order, self.active, self.peak = [], 0, 0

    async def run(self, action, payload):
        self.active += 1
        self.peak = max(self.peak, self.active)
        self.order.append(payload.get("tag"))
        try:
            await asyncio.sleep(self.delay)
            if self.fail:
                raise ValueError("falhou")
            return f"ok:{payload.get('tag')}"
        finally:
            self.active -= 1


def orch(agent, memory=None, conc=2, queue=8, timeout=5.0, coord=None):
    reg = AgentRegistry()
    reg.register(agent)
    sched = ResourceScheduler(memory or mem(est={agent.name: 100}), conc, queue)
    return Orchestrator(ActionRouter(reg), sched, timeout, coord)


# --- MemoryManager ---
def test_memory_reserve_release_headroom():
    m = mem(avail=1000, headroom=200)
    assert m.try_reserve("a", 500) and not m.try_reserve("b", 400)   # 500+400 > 1000-200
    assert m.try_reserve("c", 300) and m.reserved_mb() == 800
    m.release("a")
    assert m.try_reserve("b", 400)
    with pytest.raises(ValueError):
        m.try_reserve("b", 1)
    m.release("zzz")  # idempotente
    assert not m.could_ever_fit(9000) and m.could_ever_fit(7000)


# --- Scheduler ---
def J(i, p=NORMAL, mb=10):
    return Job(i, "ag", "act", p, mb)


def test_scheduler_priority_then_fifo_and_concurrency_limit():
    s = ResourceScheduler(mem(), max_concurrent=1, max_queue=10)
    for j in (J("l", LOW), J("n1"), J("h", HIGH), J("n2")):
        s.submit(j)
    order = []
    while (j := s.next_runnable()):
        order.append(j.id)
        assert s.next_runnable() is None          # limite de concorrência
        s.finished(j.id)
    assert order == ["h", "n1", "n2", "l"]


def test_scheduler_queue_limit_and_admission_and_cancel():
    s = ResourceScheduler(mem(total=1000), max_concurrent=1, max_queue=2)
    s.submit(J("a")); s.submit(J("b"))
    with pytest.raises(QueueFull):
        s.submit(J("c"))
    with pytest.raises(AdmissionError):
        ResourceScheduler(mem(total=1000), 1, 5).submit(J("big", mb=5000))
    assert s.cancel_queued("a") and not s.cancel_queued("a")
    assert s.next_runnable().id == "b"


def test_scheduler_skips_job_that_does_not_fit_and_reserves_memory():
    m = mem(avail=1000)
    s = ResourceScheduler(m, max_concurrent=3, max_queue=5)
    s.submit(J("grande", HIGH, mb=1500)); s.submit(J("pequeno", LOW, mb=100))
    assert s.next_runnable().id == "pequeno"       # grande não cabe agora
    assert m.reserved_mb() == 100
    assert s.snapshot()["queued"] == ["grande"]
    s.finished("pequeno")
    assert m.reserved_mb() == 0


# --- Orchestrator (concorrência real com asyncio) ---
def test_orchestrator_never_exceeds_concurrency_and_releases_memory():
    async def go():
        agent = Slow("ag", "act")
        o = orch(agent, conc=2)
        res = await asyncio.gather(*(o.run("act", {"tag": i}) for i in range(8)))
        assert [r[0] for r in res] == [f"ok:{i}" for i in range(8)]
        assert agent.peak == 2
        assert o.scheduler.memory.reserved_mb() == 0 and not o.snapshot()["running"]
        assert len(o.snapshot()["recent"]) == 8 and {m["status"] for m in o.snapshot()["recent"]} == {"done"}
    asyncio.run(go())


def test_orchestrator_priority_order_with_single_slot():
    async def go():
        agent = Slow("ag", "act", delay=0.02)
        o = orch(agent, conc=1)
        t = [asyncio.create_task(o.run("act", {"tag": "first"}))]
        await asyncio.sleep(0.005)                 # "first" já está rodando
        t.append(asyncio.create_task(o.run("act", {"tag": "low"}, LOW)))
        t.append(asyncio.create_task(o.run("act", {"tag": "high"}, HIGH)))
        await asyncio.gather(*t)
        assert agent.order == ["first", "high", "low"]
    asyncio.run(go())


def test_orchestrator_timeout_frees_slot():
    async def go():
        o = orch(Slow("ag", "act", delay=5), conc=1, timeout=0.1)
        with pytest.raises(JobTimeout):
            await o.run("act", {})
        assert o.scheduler.memory.reserved_mb() == 0 and not o.snapshot()["running"]
        assert o.snapshot()["recent"][-1]["status"] == "timeout"
    asyncio.run(go())


def test_orchestrator_agent_error_propagates_and_frees_slot():
    async def go():
        o = orch(Slow("ag", "act", fail=True), conc=1)
        for _ in range(3):                          # se vazasse slot, o 2º travaria
            with pytest.raises(ValueError):
                await asyncio.wait_for(o.run("act", {}), 2)
        assert [m["status"] for m in o.snapshot()["recent"]] == ["error"] * 3
    asyncio.run(go())


def test_orchestrator_cancel_running_and_queued():
    async def go():
        o = orch(Slow("ag", "act", delay=5), conc=1)
        t1 = asyncio.create_task(o.run("act", {}))
        t2 = asyncio.create_task(o.run("act", {}))
        await asyncio.sleep(0.05)
        snap = o.snapshot()
        assert len(snap["running"]) == 1 and len(snap["queued"]) == 1
        queued, running = snap["queued"][0], snap["running"][0]
        assert o.cancel(queued)
        with pytest.raises(JobCancelled):
            await t2
        assert o.cancel(running)
        with pytest.raises(JobCancelled):
            await t1
        assert not o.cancel("job-999") and o.scheduler.memory.reserved_mb() == 0
    asyncio.run(go())


def test_orchestrator_client_disconnect_cancels_job():
    async def go():
        agent = Slow("ag", "act", delay=5)
        o = orch(agent, conc=1)
        t = asyncio.create_task(o.run("act", {}))
        await asyncio.sleep(0.05)
        t.cancel()
        await asyncio.sleep(0.05)
        assert agent.active == 0 and not o.snapshot()["running"]
    asyncio.run(go())


def test_orchestrator_queue_full_and_unknown_action():
    async def go():
        o = orch(Slow("ag", "act", delay=1), conc=1, queue=1)
        tasks = [asyncio.create_task(o.run("act", {})) for _ in range(2)]   # 1 roda, 1 na fila
        await asyncio.sleep(0.05)
        with pytest.raises(QueueFull):
            await o.run("act", {})
        from app.core.models import RouteError
        with pytest.raises(RouteError):
            await o.run("nada", {})
        for t in tasks:
            t.cancel()
    asyncio.run(go())


# --- Locks e coordenação (processos cooperativos) ---
def test_filelock_mutual_exclusion_across_threads(tmp_path):
    counter = {"n": 0, "inside": 0, "max": 0}

    def work():
        for _ in range(20):
            with FileLock(tmp_path / "l.lock", timeout=10, poll=0.001):
                counter["inside"] += 1
                counter["max"] = max(counter["max"], counter["inside"])
                v = counter["n"]
                time.sleep(0.0005)
                counter["n"] = v + 1
                counter["inside"] -= 1
    ts = [threading.Thread(target=work) for _ in range(4)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert counter["n"] == 80 and counter["max"] == 1 and not (tmp_path / "l.lock").exists()


def test_filelock_timeout_and_stale_takeover(tmp_path):
    p = tmp_path / "x.lock"
    with FileLock(p):
        with pytest.raises(LockTimeout):
            FileLock(p, timeout=0.1, poll=0.01).acquire()
    p.write_text(json.dumps({"pid": 2**22 + 12345, "ts": time.time(), "owner": "morto"}))   # dono inexistente
    assert try_create(p, "novo", ttl=60)
    p.write_text(json.dumps({"pid": os.getpid(), "ts": time.time() - 1000, "owner": "velho"}))  # lease expirado
    assert try_create(p, "novo", ttl=60)
    p.write_text("lixo ilegível")
    assert not try_create(p, "novo", ttl=60)         # recente e ilegível: não toma
    p.unlink()


def test_coordinator_capacity_and_release(tmp_path):
    c = ResourceCoordinator(tmp_path / "c", capacity=2)
    a, b = c.try_acquire("x"), c.try_acquire("y")
    assert a and b and c.try_acquire("z") is None and c.in_use() == 2
    a.release()
    assert c.try_acquire("z") and c.in_use() == 2
    with pytest.raises(ValueError):
        ResourceCoordinator(tmp_path, 0)


def test_orchestrator_heavy_jobs_respect_shared_coordinator(tmp_path):
    async def go():
        coord_dir = tmp_path / "c"
        agent = Slow("ag", "act", delay=0.05)
        o = orch(agent, mem(est={"ag": 500}), conc=4, coord=ResourceCoordinator(coord_dir, 1))
        await asyncio.gather(*(o.run("act", {}) for _ in range(4)))
        assert agent.peak == 1                        # 4 permitidos, mas 1 slot compartilhado
        assert not list(coord_dir.glob("*.lease"))
    asyncio.run(go())


def test_patch_apply_uses_lock_and_leaves_none_behind(tmp_path):
    root = tmp_path / "w"; root.mkdir(); (root / "a.py").write_text("x=1\n")
    pm = PatchManager(Workspace(root))
    pm.apply(pm.propose("a.py", "x=2\n").id, authorized=True)
    pm.undo()
    assert not (root / ".swarm" / "patch.lock").exists()
    (root / ".swarm" / "patch.lock").write_text(json.dumps({"pid": os.getpid(), "ts": time.time(), "owner": "outro"}))
    p = pm.propose("a.py", "x=3\n")
    import app.core.locking as L
    orig = L.FileLock.__init__
    L.FileLock.__init__ = lambda self, *a, **k: orig(self, *a, **{**k, "timeout": 0.1})
    try:
        with pytest.raises(LockTimeout):
            pm.apply(p.id, authorized=True)
    finally:
        L.FileLock.__init__ = orig
    assert (root / "a.py").read_text() == "x=1\n"


# --- API ---
class P:
    name = "p"
    async def generate(self, model, prompt, system=None):
        await asyncio.sleep(0.3)
        return "r"
    async def list_models(self): return ["qwen2.5:0.5b", "qwen2.5-coder:0.5b"]


def test_api_scheduler_and_limits(tmp_path):
    s = Settings(state_path=tmp_path / "s.db", max_concurrent=1, max_queue=0, job_timeout=0.1)
    c = TestClient(create_app(s, provider=P(), memory=mem(avail=8000)))
    assert c.post("/run", json={"action": "chat", "payload": {"text": "x"}, "priority": "urgente"}).status_code == 422
    assert c.post("/run", json={"action": "chat", "payload": {"text": "x"}}).status_code == 504   # timeout 0.1 < 0.3
    snap = c.get("/scheduler").json()
    assert snap["running"] == [] and snap["recent"][-1]["status"] == "timeout" and snap["max_queue"] == 0
    assert c.post("/scheduler/jobs/job-99/cancel").status_code == 404
    assert c.post("/scheduler/jobs/job-1/cancel", headers={"origin": "http://evil.example"}).status_code == 403


def test_api_run_returns_job_id_and_admission_error(tmp_path):
    s = Settings(state_path=tmp_path / "s.db", job_timeout=5)
    c = TestClient(create_app(s, provider=P(), memory=mem(avail=8000, total=8000)))
    r = c.post("/run", json={"action": "chat", "payload": {"text": "x"}, "priority": "high"})
    assert r.status_code == 200 and r.json()["job_id"].startswith("job-")
    tiny = TestClient(create_app(s, provider=P(), memory=mem(avail=100, total=100, est={"chat": 5000})))
    assert tiny.post("/run", json={"action": "chat", "payload": {"text": "x"}}).status_code == 503
