import json
import os
import subprocess

import pytest

from cineforja import editing
from cineforja.editing import EditError

pytestmark = pytest.mark.skipif(not (editing.shutil.which("ffmpeg") and editing.shutil.which("ffprobe")),
                                reason="ffmpeg/ffprobe ausentes")


def ff(*args):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], check=True)


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height,r_frame_rate:format=duration",
                          "-of", "json", path], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


@pytest.fixture
def media(tmp_path):
    clip1, clip2, img = tmp_path / "a.mp4", tmp_path / "b.mp4", tmp_path / "c.png"
    ff("-f", "lavfi", "-i", "testsrc=s=640x360:r=30:d=1", "-pix_fmt", "yuv420p", str(clip1))
    ff("-f", "lavfi", "-i", "testsrc2=s=320x240:r=25:d=1", "-pix_fmt", "yuv420p", str(clip2))
    ff("-f", "lavfi", "-i", "color=c=red:s=100x100:d=1", "-frames:v", "1", str(img))
    return [str(clip1), str(clip2), str(img)]


def test_assemble_mixed_inputs_normalised(media, tmp_path):
    out = editing.assemble(media, str(tmp_path / "o" / "final.mp4"), width=640, height=360, fps=24, image_seconds=2)
    info = probe(out)
    v = [s for s in info["streams"] if s["codec_type"] == "video"][0]
    assert (v["width"], v["height"], v["r_frame_rate"]) == (640, 360, "24/1")
    assert 3.8 <= float(info["format"]["duration"]) <= 4.3  # 1s + 1s + 2s (imagem)


def test_assemble_with_audio(media, tmp_path):
    wav = tmp_path / "m.wav"
    ff("-f", "lavfi", "-i", "sine=f=440:d=10", str(wav))
    out = editing.assemble(media, str(tmp_path / "f.mp4"), audio=str(wav), width=320, height=180)
    info = probe(out)
    assert {s["codec_type"] for s in info["streams"]} == {"video", "audio"}
    assert float(info["format"]["duration"]) < 5  # -shortest corta o áudio de 10s


def test_missing_audio_file_is_ignored(media, tmp_path):
    out = editing.assemble(media, str(tmp_path / "f.mp4"), audio="trilha.wav", width=320, height=180)
    assert {s["codec_type"] for s in probe(out)["streams"]} == {"video"}


def test_corrupt_image_fails_fast_instead_of_hanging(tmp_path):
    # Antes do -xerror, o ffmpeg ficava em loop infinito com -loop 1 e uma imagem corrompida.
    bad = tmp_path / "bad.png"; bad.write_bytes(b"PNGDATA")
    with pytest.raises(EditError, match="falhou"):
        editing.assemble([str(bad)], str(tmp_path / "x.mp4"))
    assert not os.path.exists(tmp_path / "x.mp4")


def test_non_media_file_rejected_by_probe(tmp_path):
    bad = tmp_path / "bad.mp4"; bad.write_text("isto não é vídeo")
    with pytest.raises(EditError, match="inválido"):
        editing.assemble([str(bad)], str(tmp_path / "x.mp4"))


def test_usable_inputs():
    assert editing.usable_inputs([]) is None
    assert editing.usable_inputs(["nao_existe.mp4"]) is None
    assert editing.usable_inputs([None]) is None
