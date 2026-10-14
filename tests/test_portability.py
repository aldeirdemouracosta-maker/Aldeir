"""Correções de portabilidade Linux/Windows. Cada teste reproduz o problema encontrado na sondagem."""
import os
import sys
import time

import psutil
import pytest

from app.terminal import patches
from app.terminal.patches import PatchManager
from app.terminal.processes import LimitedProcess
from app.terminal.workspace import Workspace, WorkspaceError


@pytest.fixture
def ws(tmp_path):
    root = tmp_path / "w"
    root.mkdir()
    return Workspace(root)


# ---------- nomes seguros nos dois sistemas ----------
@pytest.mark.parametrize("name", [
    "a.txt:segredo",        # fluxo de dados alternativo do NTFS
    "nul", "NUL", "con", "CON.txt", "aux.py", "prn", "com1", "COM9.log", "lpt1", "LPT3.md",   # dispositivos
    "a.txt ", "a.txt.", "dir./x.py", "dir /x.py",                                              # ponto/espaço no fim
    "a<b.txt", "a>b", 'a"b', "a|b", "a?b", "a*b", "a\x01b", "sub/com1/x.py",
])
def test_windows_unsafe_names_are_refused_everywhere(ws, name):
    with pytest.raises(WorkspaceError, match="inseguro no Windows|inválido"):
        ws.resolve(name, must_exist=False)
    with pytest.raises(WorkspaceError):
        PatchManager(ws).propose(name, "x\n")


@pytest.mark.parametrize("name", ["ok.txt", "console.py", "nulo.txt", "com.py", "auxiliar/x.md", "a.b.c", "lpt.txt",
                                  "relatório.md", "São Paulo/ação.py", "com10.txt", "sub/dir/arquivo-1_2.py", ".gitignore"])
def test_normal_names_still_work(ws, name):
    assert ws.resolve(name, must_exist=False).name == name.split("/")[-1]


# ---------- timeout mata a árvore, não só o processo ----------
def test_timeout_kills_grandchildren(tmp_path):
    pidf = tmp_path / "grandchild.pid"
    code = ("import subprocess, sys, time\n"
            "c = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
            f"open(r'{pidf}', 'w').write(str(c.pid))\n"
            "time.sleep(60)\n")
    r = LimitedProcess([sys.executable, "-c", code], tmp_path, timeout=1.5).run()
    assert r.timed_out
    grandchild = int(pidf.read_text())
    for _ in range(40):                                        # o SO leva alguns ms para limpar
        if not psutil.pid_exists(grandchild) or psutil.Process(grandchild).status() == psutil.STATUS_ZOMBIE:
            break
        time.sleep(0.05)
    else:
        psutil.Process(grandchild).kill()
        pytest.fail("o processo-neto sobreviveu ao timeout")


def test_interrupt_kills_grandchildren_too(tmp_path, monkeypatch):
    import subprocess
    pidf = tmp_path / "gc.pid"
    code = ("import subprocess, sys, time\n"
            "c = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
            f"open(r'{pidf}', 'w').write(str(c.pid))\n"
            "time.sleep(60)\n")
    real_wait = subprocess.Popen.wait
    calls = {"n": 0}

    def wait(self, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            for _ in range(100):                               # espera o neto existir antes de "apertar Ctrl+C"
                if pidf.exists() and pidf.read_text():
                    break
                time.sleep(0.05)
            raise KeyboardInterrupt
        return real_wait(self, timeout)
    monkeypatch.setattr(subprocess.Popen, "wait", wait)
    with pytest.raises(KeyboardInterrupt):
        LimitedProcess([sys.executable, "-c", code], tmp_path, timeout=30).run()
    gc = int(pidf.read_text())
    for _ in range(40):
        if not psutil.pid_exists(gc) or psutil.Process(gc).status() == psutil.STATUS_ZOMBIE:
            return
        time.sleep(0.05)
    psutil.Process(gc).kill()
    pytest.fail("o neto sobreviveu ao Ctrl+C")


# ---------- escrita atômica resiste a bloqueio momentâneo (Windows) ----------
def test_atomic_write_retries_on_permission_error(ws, monkeypatch):
    (ws.root / "a.py").write_text("x = 1\n")
    real = os.replace
    calls = {"n": 0}

    def flaky(src, dst):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise PermissionError("arquivo em uso por outro processo")
        return real(src, dst)
    monkeypatch.setattr(patches.os, "replace", flaky)
    monkeypatch.setattr(patches.time, "sleep", lambda s: None)
    pm = PatchManager(ws)
    pm.apply(pm.propose("a.py", "x = 2\n").id, authorized=True)
    assert (ws.root / "a.py").read_text() == "x = 2\n" and calls["n"] == 3


def test_atomic_write_gives_up_cleanly_and_leaves_no_temp_file(ws, monkeypatch):
    (ws.root / "a.py").write_text("x = 1\n")

    def locked(src, dst):
        raise PermissionError("sempre em uso")
    monkeypatch.setattr(patches.os, "replace", locked)
    monkeypatch.setattr(patches.time, "sleep", lambda s: None)
    pm = PatchManager(ws)
    with pytest.raises(PermissionError):
        pm.apply(pm.propose("a.py", "x = 2\n").id, authorized=True)
    assert (ws.root / "a.py").read_text() == "x = 1\n"
    assert not [p for p in ws.root.iterdir() if p.name.startswith(".swarm-")]      # sem lixo temporário


# ---------- cosseno falha alto em vez de truncar ----------
def test_cosine_rejects_mismatched_dimensions():
    from app.multimodal.documents import cosine
    with pytest.raises(ValueError):
        cosine([1.0, 0.0], [1.0])
