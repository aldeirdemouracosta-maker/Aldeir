import io
import subprocess
import sys
from pathlib import Path

from app.stdio import utf8_stdio

ROOT = Path(__file__).resolve().parent.parent


def test_utf8_stdio_survives_a_cp1252_stream(monkeypatch):
    """Reproduz o console redirecionado do Windows: sem a correção, '→' levanta UnicodeEncodeError."""
    raw = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(raw, encoding="cp1252"))
    try:
        print("→")
        raise AssertionError("o fluxo cp1252 deveria ter falhado")
    except UnicodeEncodeError:
        pass
    utf8_stdio()
    print("passo → ok ção")
    sys.stdout.flush()
    assert "passo → ok ção".encode() in raw.getvalue()


def test_utf8_stdio_ignores_streams_without_reconfigure(monkeypatch):
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    monkeypatch.setattr(sys, "stderr", io.StringIO())
    utf8_stdio()                                           # não pode levantar


def test_cli_and_smoke_run_under_a_cp1252_console():
    """Subprocesso com PYTHONIOENCODING=cp1252 e saída em pipe, como `| Tee-Object` no PowerShell."""
    env = {"PYTHONIOENCODING": "cp1252", "PYTHONPATH": str(ROOT)}
    import os
    r = subprocess.run([sys.executable, "-m", "app.cli.main", "run", "lang_detect", "The cat is on the table and it is not happy"],
                       cwd=ROOT, capture_output=True, env={**os.environ, **env}, timeout=60)
    assert r.returncode == 0 and r.stdout.decode("utf-8").strip().startswith("en"), r.stderr.decode(errors="replace")
    r = subprocess.run([sys.executable, "scripts/smoke.py", "--url", "http://127.0.0.1:1", "--timeout", "2"],
                       cwd=ROOT, capture_output=True, env={**os.environ, **env}, timeout=60)
    assert b"UnicodeEncodeError" not in r.stderr and b"provedor" in r.stdout    # falha limpa de conexão, sem estourar a codificação


def test_cli_run_takes_text_as_positional_argument_and_path_as_option(tmp_path, monkeypatch):
    """Regressão: `swarm run ACAO "texto"` (uso documentado) chegou a virar `--text` por engano."""
    from typer.testing import CliRunner

    import app.cli.main as cm
    monkeypatch.setenv("SWARM_MEDIA", str(tmp_path / "m"))
    r = CliRunner().invoke(cm.app, ["run", "lang_detect", "The cat is on the table and it is not happy"])
    assert r.exit_code == 0 and r.output.strip().startswith("en"), r.output
    r = CliRunner().invoke(cm.app, ["run", "ocr_extract", "--path", "nao-existe.png"])      # --path é opção; falha limpa
    assert r.exit_code == 1 and "erro" in r.output.lower()
