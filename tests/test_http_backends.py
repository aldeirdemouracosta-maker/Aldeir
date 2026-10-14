import asyncio
import time

import pytest

from app.config import Settings
from app.core.models import ProviderError, UnavailableError
from app.main import build_service
from app.multimodal.documents import DocumentIndex
from app.multimodal.http_backends import LlamaServerVisionBackend, OpenAIAudioBackend
from tests.fake_servers import AudioHandler, AudioNoVerboseHandler, Server, VisionHandler, wav_bytes
from tests.helpers import wav_info

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24


def run(c):
    return asyncio.run(c)


@pytest.fixture
def audio():
    with Server(AudioHandler) as s:
        yield s


# ---------- áudio ----------
def test_transcribe_sends_valid_multipart_and_reads_language(audio, tmp_path):
    f = tmp_path / "a.wav"
    f.write_bytes(wav_bytes())
    be = OpenAIAudioBackend(audio.url, stt_model="whisper-small", timeout=5)
    assert be.transcribe(f) == ("olá mundo", "portuguese")
    req = next(r for r in audio.requests if r["path"] == "/v1/audio/transcriptions")["body"]["_multipart"]
    assert req["file"][0] == "a.wav" and req["file"][1] == wav_bytes()
    assert req["model"][1] == b"whisper-small" and req["response_format"][1] == b"verbose_json"


def test_transcribe_falls_back_when_server_lacks_verbose_json(tmp_path):
    f = tmp_path / "a.wav"
    f.write_bytes(wav_bytes())
    with Server(AudioNoVerboseHandler) as s:
        assert OpenAIAudioBackend(s.url, timeout=5).transcribe(f) == ("olá mundo", "und")
        fmts = [r["body"]["_multipart"]["response_format"][1] for r in s.requests if r["method"] == "POST"]
        assert fmts == [b"verbose_json", b"json"]


def test_synthesize_decodes_wav_and_voice_list_is_honest(audio):
    be = OpenAIAudioBackend(audio.url, tts_model="kokoro", voices=["pm_alex", "pf_dora"], timeout=5)
    samples, rate = be.synthesize("Olá", "pf_dora")
    assert rate == 8000 and len(samples) == 800 and 0.1 < max(samples) <= 1.0
    sent = next(r for r in audio.requests if r["path"] == "/v1/audio/speech")["body"]
    assert sent == {"input": "Olá", "voice": "pf_dora", "response_format": "wav", "model": "kokoro"}
    assert be.voices() == ["pf_dora", "pm_alex"]
    with pytest.raises(UnavailableError, match="SWARM_VOICE_LIST"):
        OpenAIAudioBackend(audio.url).voices()


def test_audio_errors_are_clear(audio, tmp_path):
    be = OpenAIAudioBackend(audio.url, timeout=5)
    bad = tmp_path / "x.wav"
    bad.write_bytes(b"isto nao e wav")
    with pytest.raises(ProviderError, match="HTTP 400"):
        be.transcribe(bad)
    with pytest.raises(ProviderError, match="HTTP 400"):
        be.synthesize("", "v")                        # texto vazio: o servidor recusa
    down = OpenAIAudioBackend("http://127.0.0.1:1", timeout=1)
    ok, why = down.probe()
    assert ok is False and "indisponível" in why
    with pytest.raises(ProviderError, match="indisponível"):
        down.synthesize("oi", "v")


def test_probe_is_cached_so_the_dashboard_does_not_hammer_the_server(audio):
    be = OpenAIAudioBackend(audio.url, timeout=5)
    for _ in range(20):
        assert be.probe() == (True, "ok")
    assert sum(1 for r in audio.requests if r["path"] == "/v1/models") == 1


def test_probe_of_dead_server_is_fast_and_never_blocks_the_event_loop():
    """available() roda o probe em thread: outra tarefa continua andando enquanto o servidor não responde."""
    from app.agents.speech import SpeechAgent
    from app.multimodal.service import MultimodalService
    from app.multimodal.assets import AssetStore
    import tempfile
    import socket
    hole = socket.socket()                 # aceita a conexão (backlog) e nunca responde: atraso determinístico
    hole.bind(("127.0.0.1", 0))
    hole.listen(1)
    svc = MultimodalService(AssetStore(tempfile.mkdtemp()), DocumentIndex(), None, "m",
                            speech=OpenAIAudioBackend(f"http://127.0.0.1:{hole.getsockname()[1]}", timeout=1.0))

    async def go():
        ticks = 0

        async def ticker():
            nonlocal ticks
            while True:
                await asyncio.sleep(0.05)
                ticks += 1
        t = asyncio.create_task(ticker())
        t0 = time.perf_counter()
        ok, why = await SpeechAgent(svc).available()
        dt = time.perf_counter() - t0
        t.cancel()
        return ok, dt, ticks
    try:
        ok, dt, ticks = run(go())
    finally:
        hole.close()
    assert ok is False and 0.8 < dt < 4 and ticks >= 5      # o probe demorou e o loop seguiu rodando


# ---------- visão ----------
def test_vision_sends_data_uri_and_strips_thinking(tmp_path):
    img = tmp_path / "f.png"
    img.write_bytes(PNG)
    with Server(VisionHandler) as s:
        be = LlamaServerVisionBackend(s.url, model="smolvlm-256m", timeout=5)
        assert be.probe() == (True, "ok")
        out = be.describe(img, "O que é?")
        assert out == f"Imagem de {len(PNG)} bytes. Pedido: O que é?"
        body = next(r for r in s.requests if r["path"] == "/v1/chat/completions")["body"]
        assert body["model"] == "smolvlm-256m" and body["stream"] is False
    bad = tmp_path / "x.png"
    bad.write_bytes(b"GIF89a....")
    with pytest.raises(UnavailableError):
        LlamaServerVisionBackend("http://127.0.0.1:1").describe(bad, "x")


# ---------- integração: serviço e API usando os backends HTTP ----------
def test_service_wires_http_backends_from_settings(tmp_path):
    with Server(AudioHandler) as a, Server(VisionHandler) as v:
        s = Settings(media_dir=tmp_path / "m", audio_url=a.url, vision_url=v.url, voice_list=("pf_dora",), request_timeout=5)
        svc = build_service(s, None, index=DocumentIndex())
        assert isinstance(svc.speech, OpenAIAudioBackend) and svc.speech is svc.voice
        assert isinstance(svc.vision, LlamaServerVisionBackend)
        (svc.assets.root / "a.wav").write_bytes(wav_bytes())
        (svc.assets.root / "f.png").write_bytes(PNG)
        assert run(svc.transcribe("a.wav")) == "[portuguese] olá mundo"
        assert run(svc.list_voices()) == ["pf_dora"]
        out = run(svc.speak("Olá mundo", "pf_dora"))
        assert out.startswith("out/") and wav_info(svc.assets.root / out)["rate"] == 8000
        assert "Imagem de" in run(svc.describe_image("f.png", "descreva"))
