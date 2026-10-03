import struct
from io import BytesIO

from PIL import Image

from frameltx.backends import GenParams
from frameltx.comfy_client import ComfyClient, ComfyOOMError, _friendly_execution_error
from frameltx.presets import PRESETS, build_prompts
from frameltx.storage import HistoryEntry, Storage, slugify
from frameltx.vram import GpuInfo, lower_profile, profile_for_vram, resolve_profile


def test_profile_by_vram():
    assert profile_for_vram(6).key == "baixo"
    assert profile_for_vram(8).key == "medio"
    assert profile_for_vram(12).key == "alto"
    assert profile_for_vram(24).key == "ultra"
    assert profile_for_vram(None).key == "medio"


def test_profile_dimensions_are_valid():
    from frameltx.vram import PROFILES
    for p in PROFILES:
        assert p.fp_width % 16 == 0 and p.fp_height % 16 == 0
        assert p.ltx_width % 32 == 0 and p.ltx_height % 32 == 0


def test_force_profile_and_lowering():
    assert resolve_profile("alto", GpuInfo("x", 6)).key == "alto"
    low = profile_for_vram(6)
    emergency = lower_profile(low)
    assert emergency is not None and emergency.fp_width < low.fp_width
    assert lower_profile(emergency) is None


def test_ltx_length_is_8n_plus_1():
    for secs in (1, 3.3, 5, 8):
        n = GenParams("p", "n", 64, 64, secs, 24, 1, 8).ltx_length
        assert (n - 1) % 8 == 0


def test_build_prompts():
    pos, neg = build_prompts("", "Produto girando", "Comercial")
    assert PRESETS["Produto girando"].default_prompt in pos and "rotates" in pos
    assert "blurry" in neg
    pos, _ = build_prompts("um gato", "Livre", "Anime")
    assert pos.startswith("um gato") and "anime" in pos


def test_slugify():
    assert slugify("Ação: gato pulando!!") == "acao-gato-pulando"
    assert slugify("") == "video"


def test_history_roundtrip(tmp_path):
    storage = Storage(tmp_path)
    video = storage.new_output_base("ltx", "teste").with_suffix(".mp4")
    video.write_bytes(b"x")
    entry = HistoryEntry("id1", "2026-01-01T10:00:00", "ltx", "teste", "Livre", "Realista", 5, "medio", 1, str(video))
    storage.add_entry(entry)
    assert [e.id for e in storage.load_history()] == ["id1"]
    storage.delete_entry("id1")
    assert storage.load_history() == [] and not video.exists()


def test_oom_detection():
    err = _friendly_execution_error({"node_type": "FramePackSampler", "exception_message": "CUDA out of memory."})
    assert isinstance(err, ComfyOOMError) and "VRAM insuficiente" in str(err)


def test_preview_decoding():
    buf = BytesIO()
    Image.new("RGB", (8, 8)).save(buf, "JPEG")
    img = ComfyClient._decode_preview(struct.pack(">II", 1, 1) + buf.getvalue())
    assert img is not None and img.size == (8, 8)
    assert ComfyClient._decode_preview(b"\x00") is None
