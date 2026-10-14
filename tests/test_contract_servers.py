"""Nossos clientes contra servidores HTTP reais que seguem os contratos documentados."""
import asyncio
import subprocess
import sys
from pathlib import Path

import pytest

from app.core.models import ProviderError
from app.providers.local_compatible import LocalCompatibleProvider
from app.providers.ollama import OllamaProvider
from tests.fake_servers import CHAT, EMBED, OllamaHandler, OpenAIHandler, Server

ROOT = Path(__file__).resolve().parent.parent


def run(c):
    return asyncio.run(c)


@pytest.fixture
def ollama():
    with Server(OllamaHandler) as s:
        yield s


@pytest.fixture
def openai():
    with Server(OpenAIHandler) as s:
        yield s


def test_ollama_provider_over_real_http(ollama):
    async def go():
        p = OllamaProvider(ollama.url, timeout=5)
        try:
            assert CHAT in await p.list_models()
            assert await p.loaded_models() == [CHAT]
            assert await p.generate(CHAT, "oi", system="Resuma") == "Resumo: lançamento em março."
            v = await p.embed(EMBED, "o gato dorme")
            assert v == [1.0, 0.0, 0.1]
        finally:
            await p.aclose()
    run(go())
    gen = next(r for r in ollama.requests if r["path"] == "/api/generate")["body"]
    assert gen["stream"] is False and gen["model"] == CHAT and gen["system"] == "Resuma"
    emb = next(r for r in ollama.requests if r["path"] == "/api/embed")["body"]
    assert emb == {"model": EMBED, "input": "o gato dorme"}


def test_openai_compatible_provider_over_real_http(openai):
    async def go():
        p = LocalCompatibleProvider(openai.url, timeout=5)
        try:
            assert CHAT in await p.list_models()
            assert await p.generate(CHAT, "oi", system="Traduza") == "Good morning, how are you?"
            assert await p.embed(EMBED, "um carro") == [0.0, 1.0, 0.1]
        finally:
            await p.aclose()
    run(go())
    chat = next(r for r in openai.requests if r["path"] == "/v1/chat/completions")["body"]
    assert [m["role"] for m in chat["messages"]] == ["system", "user"] and chat["stream"] is False


def test_providers_report_unreachable_server_cleanly():
    async def go():
        for cls in (OllamaProvider, LocalCompatibleProvider):
            p = cls("http://127.0.0.1:1", timeout=1)      # porta fechada
            with pytest.raises(ProviderError):
                await p.list_models()
            with pytest.raises(ProviderError):
                await p.generate("m", "x")
            await p.aclose()
    run(go())


class _Erro500(OllamaHandler):
    def post(self, b):
        self._json(500, {"error": "modelo falhou ao carregar"})


def test_server_5xx_becomes_provider_error_with_status():
    async def go():
        with Server(_Erro500) as srv:
            p = OllamaProvider(srv.url, timeout=5)
            with pytest.raises(ProviderError, match="500"):
                await p.generate(CHAT, "oi")
            with pytest.raises(ProviderError, match="500"):
                await p.embed(EMBED, "oi")
            await p.aclose()
    run(go())


@pytest.mark.parametrize("provider,fixture", [("ollama", "ollama"), ("local_compatible", "openai")])
def test_smoke_script_passes_against_contract_server(provider, fixture, request):
    """O próprio scripts/smoke.py roda de ponta a ponta (subprocesso) contra um servidor de contrato."""
    srv = request.getfixturevalue(fixture)
    r = subprocess.run([sys.executable, "scripts/smoke.py", "--provider", provider, "--url", srv.url, "--timeout", "30"],
                       cwd=ROOT, capture_output=True, text=True, timeout=120)
    out = r.stdout + r.stderr
    assert r.returncode == 0, out
    assert "0 falha(s)" in out and "[FALHA" not in out
    for step in ("chat", "summarize", "chat com memória de sessão", "coder code_only", "rag indexar", "langid", "planner plan_run"):
        assert f"] {step}" in out, (step, out)
    assert "] rag buscar (semântica)" in out and "[OK     ] rag buscar" in out


def test_smoke_script_covers_media_servers_end_to_end(ollama):
    from tests.fake_servers import AudioHandler, VisionHandler
    with Server(AudioHandler) as audio, Server(VisionHandler) as vision:
        r = subprocess.run([sys.executable, "scripts/smoke.py", "--url", ollama.url, "--timeout", "30",
                            "--vision-url", vision.url, "--audio-url", audio.url, "--voices", "pf_dora"],
                           cwd=ROOT, capture_output=True, text=True, timeout=120)
        out = r.stdout + r.stderr
        assert r.returncode == 0, out
        for step in ("vision (llama-server --mmproj)", "speech (contrato", "voice (gera WAV)"):
            assert f"[OK     ] {step}" in out, (step, out)
        assert "0 falha(s)" in out
