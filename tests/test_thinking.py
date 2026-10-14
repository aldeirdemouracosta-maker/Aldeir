import asyncio

import pytest

from app.providers.base import strip_think
from app.providers.local_compatible import LocalCompatibleProvider
from app.providers.ollama import OllamaProvider
from tests.fake_servers import CHAT, OllamaHandler, OpenAIHandler, Server


@pytest.mark.parametrize("raw,clean", [
    ("<think>vou pensar...</think>\n\nResposta: 4", "Resposta: 4"),
    ("<think>\nlinha 1\nlinha 2\n</think>ok", "ok"),
    ("sem raciocínio", "sem raciocínio"),
    ("<think>a</think>um<think>b</think> dois", "um dois"),
    ("<think>raciocínio cortado sem fechar", ""),          # falha visível em vez de lixo como resposta
    ("antes <think>cortado", "antes"),
    ("", ""),
])
def test_strip_think(raw, clean):
    assert strip_think(raw) == clean


class _Pensa(OllamaHandler):
    def post(self, b):
        if self.path == "/api/generate":
            return self._json(200, {"response": "<think>hmm</think>\nResposta limpa", "done": True})
        super().post(b)


class _PensaOpenAI(OpenAIHandler):
    def post(self, b):
        if self.path == "/v1/chat/completions":
            return self._json(200, {"choices": [{"message": {"content": "<think>hmm</think>Resposta limpa"}}]})
        super().post(b)


def test_both_providers_strip_thinking_over_real_http():
    async def go():
        with Server(_Pensa) as a, Server(_PensaOpenAI) as b:
            p1, p2 = OllamaProvider(a.url, timeout=5), LocalCompatibleProvider(b.url, timeout=5)
            assert await p1.generate(CHAT, "x") == "Resposta limpa"
            assert await p2.generate(CHAT, "x") == "Resposta limpa"
            await p1.aclose(); await p2.aclose()
    asyncio.run(go())


def test_manifest_has_qwen3_candidate_honestly_marked():
    from app.config import Settings
    from app.core.model_files import load_manifests
    m = load_manifests(Settings().models_file)["qwen3-0.6b-q8_0"]
    assert m.license == "Apache-2.0" and m.sha256 is None and set(m.agents) == {"chat", "coder", "planner"}
