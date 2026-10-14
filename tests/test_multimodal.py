import asyncio
import os
import struct
import wave

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.core.models import UnavailableError
from app.main import build_service, create_app
from app.multimodal.assets import AssetError, AssetStore
from app.multimodal.documents import DocumentIndex, chunk_text, cosine
from app.multimodal.executors import KokoroBackend, SmolVLMBackend, WhisperBackend
from app.multimodal.media import sine, sniff_audio, sniff_image, wav_info, write_wav
from app.terminal.workspace import WorkspaceError

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 20


def run(c):
    return asyncio.run(c)


class FakeVision:
    def probe(self): return True, "ok"
    def describe(self, image, prompt): return f"imagem {image.name}: {prompt}"


class FakeSpeech:
    def probe(self): return True, "ok"
    def transcribe(self, audio): return "olá mundo", "pt"


class FakeVoice:
    def probe(self): return True, "ok"
    def voices(self): return ["af_a", "bm_b"]
    def synthesize(self, text, voice): return sine(0.1, 8000), 8000


class Down:
    def probe(self): return False, "pesos ausentes"


class EmbProvider:
    """Embeddings determinísticos por palavras-chave: 'gato' e 'carro' têm eixos distintos."""
    name = "fake"

    async def embed(self, model, text):
        t = text.lower()
        return [float("gato" in t), float("carro" in t), 0.1]

    async def list_models(self): return ["nomic-embed-text:latest"]


@pytest.fixture
def store(tmp_path):
    return AssetStore(tmp_path / "media")


# --- media / assets ---
def test_sniffers():
    assert sniff_image(PNG) == "png" and sniff_image(JPG) == "jpeg" and sniff_image(b"GIF89a") is None
    assert sniff_audio(b"RIFF\0\0\0\0WAVE") == "wav" and sniff_audio(b"fLaC") == "flac"
    assert sniff_audio(b"MZ\x90\x00") is None


def test_write_wav_roundtrip(tmp_path):
    p = tmp_path / "a.wav"
    write_wav(p, sine(0.5, 8000), 8000)
    info = wav_info(p)
    assert info["rate"] == 8000 and info["channels"] == 1 and abs(info["seconds"] - 0.5) < 0.01
    with pytest.raises(ValueError):
        write_wav(p, [], 8000)


def test_assets_validate_type_size_and_path(store):
    (store.root / "ok.png").write_bytes(PNG)
    (store.root / "fake.png").write_bytes(b"isto nao e imagem")
    (store.root / "s.wav").write_bytes(b"RIFF\0\0\0\0WAVEfmt ")
    assert store.path("ok.png", "image").name == "ok.png"
    with pytest.raises(AssetError):
        store.path("fake.png", "image")
    with pytest.raises(AssetError):
        store.path("ok.png", "audio")
    assert store.path("s.wav", "audio")
    with pytest.raises(WorkspaceError):
        store.path("../x.png", "image")
    (store.root / "big.png").write_bytes(PNG + b"0" * (10 * 2**20))
    with pytest.raises(AssetError):
        store.path("big.png", "image")


def test_assets_reject_symlink_and_new_output_never_overwrites(store, tmp_path):
    outside = tmp_path / "fora.png"
    outside.write_bytes(PNG)
    os.symlink(outside, store.root / "l.png")
    with pytest.raises(WorkspaceError):
        store.path("l.png", "image")
    a = store.new_output("../../etc/x", "wav")
    a.write_bytes(b"1")
    b = store.new_output("../../etc/x", "wav")
    assert a != b and a.parent == store.root / "out" and b.parent == store.root / "out"


# --- RAG ---
def test_chunking_keeps_line_references():
    text = "\n".join(f"linha {i} " + "x" * 50 for i in range(1, 41))
    ch = chunk_text(text, max_chars=300)
    assert len(ch) > 1 and ch[0][0] == 1 and ch[-1][1] == 40
    assert all(a <= b for a, b, _ in ch) and chunk_text("  \n\n") == []


def test_cosine():
    assert cosine([1, 0], [1, 0]) == pytest.approx(1) and cosine([1, 0], [0, 1]) == 0 and cosine([0], [0]) == 0


def test_index_search_reindex_and_dim_mismatch():
    idx, p = DocumentIndex(), EmbProvider()
    emb = lambda t: p.embed("m", t)
    assert run(idx.index_text("a.md", "o gato dorme\n", emb, "m")) == 1
    assert run(idx.index_text("b.md", "o carro corre\n", emb, "m")) == 1
    assert run(idx.index_text("a.md", "o gato dorme\n", emb, "m")) == 0   # sem mudança: não reindexa
    top = idx.search(run(p.embed("m", "gato")), k=2)
    assert top[0]["path"] == "a.md" and top[0]["score"] > top[1]["score"]
    assert run(idx.index_text("a.md", "agora fala de carro\n", emb, "m")) == 1  # mudou: substitui
    assert idx.stats() == {"documents": 2, "chunks": 2}
    assert idx.search([1.0, 0.0]) == []      # dimensão incompatível não casa


def test_failed_embedding_keeps_previous_index():
    idx, p = DocumentIndex(), EmbProvider()
    run(idx.index_text("a.md", "gato\n", lambda t: p.embed("m", t), "m"))

    async def boom(t):
        raise RuntimeError("ollama caiu")
    with pytest.raises(RuntimeError):
        run(idx.index_text("a.md", "texto novo\n", boom, "m"))
    assert idx.stats()["chunks"] == 1 and idx.search([1.0, 0.0, 0.1])[0]["text"] == "gato"


# --- Serviço e agentes (backends simulados) ---
def service(tmp_path, **kw):
    s = Settings(media_dir=tmp_path / "media")
    return build_service(s, EmbProvider(), kw.get("vision", FakeVision()), kw.get("speech", FakeSpeech()),
                         kw.get("voice", FakeVoice()), DocumentIndex())


def test_service_vision_speech_voice(tmp_path):
    svc = service(tmp_path)
    (svc.assets.root / "f.png").write_bytes(PNG)
    (svc.assets.root / "a.wav").write_bytes(b"RIFF\0\0\0\0WAVEfmt ")
    assert run(svc.describe_image("f.png", "o que é?")) == "imagem f.png: o que é?"
    assert run(svc.transcribe("a.wav")) == "[pt] olá mundo"
    assert run(svc.list_voices()) == ["af_a", "bm_b"]
    out = run(svc.speak("oi", "af_a"))
    assert out.startswith("out/") and wav_info(svc.assets.root / out)["rate"] == 8000
    with pytest.raises(ValueError):
        run(svc.speak("x" * 2001, "af_a"))


def test_service_unavailable_backends_say_so(tmp_path):
    svc = service(tmp_path, vision=Down(), voice=Down())
    svc.speech = None
    (svc.assets.root / "f.png").write_bytes(PNG)
    with pytest.raises(UnavailableError, match="pesos ausentes"):
        run(svc.describe_image("f.png", ""))
    with pytest.raises(UnavailableError, match="não configurado"):
        run(svc.transcribe("a.wav"))
    with pytest.raises(UnavailableError):
        run(svc.speak("oi", "v"))


def test_service_rag_index_dir_and_search(tmp_path):
    svc = service(tmp_path)
    docs = svc.assets.root / "docs"
    docs.mkdir()
    (docs / "gatos.md").write_text("O gato gosta de dormir.\n")
    (docs / "carros.txt").write_text("O carro anda rápido.\n")
    (docs / "img.png").write_bytes(PNG)              # extensão não textual: ignorada
    r = run(svc.index_path("docs"))
    assert r["files"] == 2 and r["documents"] == 2
    hit = run(svc.search("gato", 1))[0]
    assert hit["path"] == "docs/gatos.md" and hit["line_start"] == 1
    with pytest.raises(WorkspaceError):
        run(svc.index_path("../fora"))


# --- API ---
@pytest.fixture
def client(tmp_path):
    svc = service(tmp_path, speech=Down())
    (svc.assets.root / "f.png").write_bytes(PNG)
    return TestClient(create_app(Settings(state_path=tmp_path / "s.db"), provider=EmbProvider(), service=svc))


def test_api_availability_is_real(client):
    a = {x["name"]: x for x in client.get("/agents").json()}
    assert a["vision"]["available"] and not a["speech"]["available"] and a["speech"]["reason"] == "pesos ausentes"
    assert a["rag"]["available"]
    st = client.get("/multimodal/status").json()
    assert st["backends"]["speech"]["available"] is False and st["limits_bytes"]["image"] == 10 * 2**20


def test_api_run_media_and_errors(client):
    r = client.post("/run", json={"action": "image_describe", "payload": {"path": "f.png", "prompt": "x"}})
    assert r.status_code == 200 and "f.png" in r.json()["output"]
    assert client.post("/run", json={"action": "speech_transcribe", "payload": {"path": "a.wav"}}).status_code == 503
    assert client.post("/run", json={"action": "image_describe", "payload": {}}).status_code == 422


def test_api_media_path_traversal_blocked(client):
    for bad in ("../../etc/passwd", "/etc/passwd"):
        r = client.post("/run", json={"action": "image_describe", "payload": {"path": bad}})
        assert r.status_code >= 400 and "describe" not in r.text


# --- Backends reais: apenas probe (sem pesos/dependências aqui) ---
def test_real_backends_report_unavailable_without_weights(tmp_path):
    for be in (SmolVLMBackend(str(tmp_path)), WhisperBackend(str(tmp_path)), KokoroBackend("", "")):
        ok, why = be.probe()
        assert ok is False and why
    with pytest.raises(UnavailableError):
        SmolVLMBackend(str(tmp_path)).describe(tmp_path / "x.png", "p")
