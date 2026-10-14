import asyncio
import os
import sys

import pytest

from app.terminal.memory import SessionMemory
from app.terminal.patches import PatchError, PatchManager
from app.terminal.processes import LimitedProcess
from app.terminal.runner import TestRunner
from app.terminal.ui import Terminal, strip_fence
from app.terminal.workspace import Workspace, WorkspaceError


@pytest.fixture
def ws(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "a.py").write_text("x = 1\n")
    (root / "sub").mkdir()
    (root / "sub" / "b.txt").write_text("alpha\nbeta\n")
    return Workspace(root)


def run(c):
    return asyncio.run(c)


# --- Workspace ---
@pytest.mark.parametrize("bad", ["../x", "sub/../../x", "/etc/passwd", "C:\\x", "", "a\x00b"])
def test_rejects_traversal_and_absolute(ws, bad):
    with pytest.raises(WorkspaceError):
        ws.resolve(bad)


def test_rejects_symlink_even_inside_root(ws):
    os.symlink(ws.root / "a.py", ws.root / "link.py")
    with pytest.raises(WorkspaceError):
        ws.read("link.py")


def test_rejects_symlink_dir_escape(ws, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "s.txt").write_text("segredo")
    os.symlink(outside, ws.root / "esc")
    with pytest.raises(WorkspaceError):
        ws.read("esc/s.txt")
    assert all("segredo" not in t for _, _, t in ws.search("segredo"))


def test_rejects_hardlink(ws, tmp_path):
    os.link(ws.root / "a.py", ws.root / "hard.py")
    with pytest.raises(WorkspaceError):
        ws.read("hard.py")


def test_read_limits_and_binary(ws):
    (ws.root / "big.txt").write_text("x" * 600_000)
    (ws.root / "bin.dat").write_bytes(b"\x00\x01")
    for name in ("big.txt", "bin.dat"):
        with pytest.raises(WorkspaceError):
            ws.read(name)


def test_search_and_tree_ignore_state_dirs(ws):
    (ws.root / ".git").mkdir()
    (ws.root / ".git" / "c").write_text("beta")
    hits = ws.search("beta")
    assert hits == [("sub/b.txt", 2, "beta")]
    assert ".git" not in ws.tree() and "sub/" in ws.tree()


# --- PatchManager ---
def test_propose_does_not_write_and_apply_requires_authorization(ws):
    pm = PatchManager(ws)
    p = pm.propose("a.py", "x = 2\n")
    assert (ws.root / "a.py").read_text() == "x = 1\n"
    assert "-x = 1" in p.diff and "+x = 2" in p.diff
    for bad in (False, None, 1, "sim"):
        with pytest.raises(PatchError):
            pm.apply(p.id, authorized=bad)
    assert (ws.root / "a.py").read_text() == "x = 1\n"


def test_apply_backup_and_undo_roundtrip(ws):
    pm = PatchManager(ws)
    pm.apply(pm.propose("a.py", "x = 2\n").id, authorized=True)
    assert (ws.root / "a.py").read_text() == "x = 2\n"
    assert len(list((ws.root / ".swarm" / "backups").iterdir())) == 1
    assert pm.undo() == "a.py"
    assert (ws.root / "a.py").read_text() == "x = 1\n"
    with pytest.raises(PatchError):
        pm.undo()


def test_new_file_undo_deletes_it_and_undo_is_lifo(ws):
    pm = PatchManager(ws)
    pm.apply(pm.propose("new/n.py", "n=1\n").id, authorized=True)
    pm.apply(pm.propose("a.py", "x = 3\n").id, authorized=True)
    pm.undo()
    assert (ws.root / "a.py").read_text() == "x = 1\n" and (ws.root / "new/n.py").exists()
    pm.undo()
    assert not (ws.root / "new/n.py").exists()


def test_conflict_detected_if_file_changed(ws):
    pm = PatchManager(ws)
    p = pm.propose("a.py", "x = 2\n")
    (ws.root / "a.py").write_text("mudou\n")
    with pytest.raises(PatchError):
        pm.apply(p.id, authorized=True)


def test_undo_refused_if_modified_after_apply(ws):
    pm = PatchManager(ws)
    pm.apply(pm.propose("a.py", "x = 2\n").id, authorized=True)
    (ws.root / "a.py").write_text("manual\n")
    with pytest.raises(PatchError):
        pm.undo()
    assert (ws.root / "a.py").read_text() == "manual\n"


def test_patch_rejects_escape_state_dir_and_noop(ws):
    pm = PatchManager(ws)
    with pytest.raises(WorkspaceError):
        pm.propose("../fora.py", "x")
    with pytest.raises(PatchError):
        pm.propose(".swarm/history.jsonl", "x")
    with pytest.raises(PatchError):
        pm.propose("a.py", "x = 1\n")


# --- Processos / runner ---
def test_limited_process_timeout_and_truncation(tmp_path):
    r = LimitedProcess([sys.executable, "-c", "import time; time.sleep(30)"], tmp_path, timeout=0.5).run()
    assert r.timed_out
    r = LimitedProcess([sys.executable, "-c", "print('x'*5000)"], tmp_path, timeout=10, max_output=100).run()
    assert "truncada" in r.output and r.returncode == 0


def test_runner_runs_pytest_in_workspace(ws):
    (ws.root / "test_ok.py").write_text("def test_ok():\n    assert True\n")
    r = TestRunner(ws, timeout=60).run()
    assert r.returncode == 0 and "1 passed" in r.output
    with pytest.raises(WorkspaceError):
        TestRunner(ws).run("../x")


# --- Memória ---
def test_session_memory_bounds_and_persistence(tmp_path):
    db = tmp_path / "s.db"
    m = SessionMemory(max_turns=2, db_path=db)
    for i in range(3):
        m.add_turn("user", f"t{i}")
    m.touch_file("a.py")
    m.set_summary("resumo")
    m.close()
    m2 = SessionMemory(max_turns=2, db_path=db)
    assert [t for _, t in m2.turns] == ["t1", "t2"]
    assert list(m2.recent_files) == ["a.py"] and m2.summary == "resumo"


# --- Terminal: fluxo /edit → /diff → /apply → /test → /undo ---
class EditProvider:
    name = "fake"

    def __init__(self, reply):
        self.reply = reply

    async def generate(self, model, prompt, system=None):
        return self.reply

    async def list_models(self):
        return []


def test_strip_fence():
    assert strip_fence("```python\nx=1\n```") == "x=1\n"
    assert strip_fence("x=1") == "x=1\n"


def test_full_supervised_flow(ws):
    (ws.root / "test_x.py").write_text("from a import x\n\ndef test_x():\n    assert x == 2\n")
    answers = iter([False, True])
    t = Terminal(ws, EditProvider("```python\nx = 2\n```"), "m", confirm=lambda q: next(answers))
    assert "proposta #1" in run(t.handle("/edit a.py mude x para 2"))
    assert (ws.root / "a.py").read_text() == "x = 1\n"
    assert "+x = 2" in run(t.handle("/diff"))
    assert "não aplicado" in run(t.handle("/apply"))            # usuário negou
    assert (ws.root / "a.py").read_text() == "x = 1\n"
    assert "aplicado" in run(t.handle("/apply 1"))               # usuário autorizou
    assert "1 passed" in run(t.handle("/test"))
    assert "desfeito" in run(t.handle("/undo"))
    assert (ws.root / "a.py").read_text() == "x = 1\n"


def test_terminal_never_executes_model_output(ws):
    marker = ws.root / "pwned"
    reply = f"import os; os.system('touch {marker}')\n"
    t = Terminal(ws, EditProvider(reply), "m", confirm=lambda q: False)
    run(t.handle("/edit a.py qualquer"))
    run(t.handle("/apply"))
    assert not marker.exists() and (ws.root / "a.py").read_text() == "x = 1\n"


def test_terminal_reports_errors_instead_of_raising(ws):
    t = Terminal(ws, EditProvider("x"), "m")
    assert run(t.handle("/read ../x")).startswith("erro:")
    assert run(t.handle("/diff")).startswith("erro:")
    assert run(t.handle("/apply abc")).startswith("erro:")
    assert "desconhecido" in run(t.handle("/rm -rf"))
