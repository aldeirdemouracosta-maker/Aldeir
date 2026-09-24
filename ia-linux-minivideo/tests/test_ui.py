import os
import shutil
import subprocess

import pytest

from minivideo_agents.workspace import FOLDERS, Workspace
from minivideo_ui.model import Browser, human_size, kind_of

pyte = pytest.importorskip("pyte")
from tui_harness import DOWN, ENTER, ESC, F1, LEFT, TAB, Tui  # noqa: E402


def test_browser_starts_in_midia_and_stays_inside_workspace(tmp_path):
    ws = Workspace(str(tmp_path / "ws"))
    assert sorted(os.listdir(ws.root)) == sorted(FOLDERS)
    b = Browser(ws)
    assert b.relative_cwd == "Midia" and b.pane == "pastas"
    b.enter()                   # vai para o painel de arquivos
    b.back()                    # na raiz da pasta, volta ao painel de pastas
    assert b.pane == "pastas" and b.relative_cwd == "Midia"
    b.move(-10)
    assert b.relative_cwd == "Projetos"
    b.move(+10)
    assert b.relative_cwd == "Logs"


def test_browser_subfolders_and_new_folder(tmp_path):
    ws = Workspace(str(tmp_path / "ws"))
    b = Browser(ws)
    b.toggle_pane()
    b.new_folder("Aula 01")
    assert b.selected.name == "Aula 01" and b.selected.kind == "pasta"
    b.enter()
    assert b.relative_cwd == os.path.join("Midia", "Aula 01")
    b.back()
    assert b.relative_cwd == "Midia" and b.selected.name == "Aula 01"
    for bad in ("../fora", "a/b", "", ".."):
        with pytest.raises(ValueError):
            b.new_folder(bad)


def test_kinds_sizes_and_default_output(tmp_path):
    assert kind_of("x.MP4", False) == "vídeo" and kind_of("m.gguf", False) == "modelo"
    assert kind_of("d", True) == "pasta" and kind_of("a.xyz", False) == "arquivo"
    assert human_size(512) == "512 B" and human_size(2048) == "2.0 KB"
    ws = Workspace(str(tmp_path / "ws"))
    b = Browser(ws)
    out = b.default_output("/x/aula.mp4")
    assert out.endswith("Saidas/aula_editado.mp4")
    open(out, "w").close()
    assert b.default_output("/x/aula.mp4").endswith("aula_editado_2.mp4")


# ---------- interface real num pseudo-terminal ----------

@pytest.fixture
def ws_with_video(tmp_path):
    ws = Workspace(str(tmp_path / "ws"))
    if shutil.which("ffmpeg"):
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=160x90:rate=10",
                        "-f", "lavfi", "-i", "sine=frequency=300", "-t", "2", "-c:v", "libx264",
                        "-pix_fmt", "yuv420p", "-c:a", "aac", os.path.join(ws.path("Midia"), "clipe.mp4")], check=True)
    else:
        open(os.path.join(ws.path("Midia"), "clipe.mp4"), "wb").close()
    return ws


def test_tui_renders_folders_help_and_navigation(ws_with_video):
    t = Tui(ws_with_video.root)
    try:
        assert t.wait_for("Q Sair")
        screen = t.text()
        assert "IA-Linux MiniVideo" in screen and "Pastas ◄" in screen
        for folder in FOLDERS:
            assert folder in screen
        assert "clipe.mp4" in screen and "vídeo" in screen
        assert "Q Sair" in screen.splitlines()[-1]
        t.send(F1)
        assert "Terminal de prompt" in t.text() or "terminal de prompt" in t.text()
        t.send(ESC)
        t.send(DOWN)
        t.send(DOWN)
        assert " > Saidas" in t.text()
        t.send(TAB)
        assert "Saidas ◄" in t.text()
        t.send(LEFT)
        assert "Pastas ◄" in t.text()
    finally:
        t.close()


def test_tui_prompt_terminal_explains_before_running(ws_with_video):
    t = Tui(ws_with_video.root)
    try:
        t.send(TAB)
        t.send("T", 0.8)
        t.send("gere um vídeo de uma praia ao pôr do sol", 0.3)
        t.send(ENTER, 1.0)
        assert t.wait_for("Plano dos especialistas (nada foi executado)")
        screen = t.text()
        assert "DIRETOR" in screen and "REJEITADO c1/gerar_video" in screen
        assert "CUDA" in screen
        t.send("e", 1.0)  # etapa bloqueada: não pode executar
        t.send(ESC)
        assert not os.listdir(ws_with_video.path("Saidas"))
    finally:
        t.close()


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg ausente")
def test_tui_executes_ffmpeg_job(ws_with_video):
    t = Tui(ws_with_video.root)
    try:
        t.send(TAB)
        t.send("T", 0.8)
        t.send("limpe o áudio", 0.3)
        t.send(ENTER, 1.0)
        assert t.wait_for("Entrada:")
        assert "FISCAL DE HARDWARE" in t.text()
        t.send("e", 1.0)
        assert t.wait_for("Continuísta: aprovado", 60)
        assert os.listdir(ws_with_video.path("Saidas")) == ["clipe_editado.mp4"]
    finally:
        t.close()
