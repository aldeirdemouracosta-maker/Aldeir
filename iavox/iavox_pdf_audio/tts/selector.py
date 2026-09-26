"""
Seletor de motor de TTS do IAVOX.

Implementa as 5 opções escolhidas:
1. offline       -> espeak-ng (sempre disponível, voz robótica)
2. piper         -> Piper TTS (offline, voz natural)
3. kokoro        -> Kokoro (voz neural leve, PT-BR nativo)
4. ia            -> Coqui TTS (voz neural via IA local, mais pesado)
5. automatico    -> tenta na ordem ia > kokoro > piper > offline, usando o
                     melhor motor realmente disponível na máquina do usuário

Cada motor recebe seus próprios parâmetros por nomes específicos (ex:
piper_model_path, kokoro_model_path) — evita colisão de nomes entre motores
que usam conceitos parecidos (Piper e Kokoro usam "model_path" internamente,
mas apontam para arquivos completamente diferentes).
"""
from __future__ import annotations

import logging

from .ai_engine import AITTSEngine
from .base import TTSEngine
from .espeak_engine import EspeakEngine
from .kokoro_engine import KokoroEngine
from .piper_engine import PiperEngine

logger = logging.getLogger("iavox.tts.selector")

ENGINE_CHOICES = ("offline", "piper", "kokoro", "ia", "automatico")


def _make_espeak(kwargs: dict) -> EspeakEngine:
    params = {}
    if kwargs.get("espeak_voice"):
        params["voice"] = kwargs["espeak_voice"]
    if kwargs.get("espeak_speed_wpm"):
        params["speed_wpm"] = kwargs["espeak_speed_wpm"]
    if kwargs.get("espeak_binary_path"):
        params["binary_path"] = kwargs["espeak_binary_path"]
    return EspeakEngine(**params)


def _make_piper(kwargs: dict) -> PiperEngine:
    params = {}
    if kwargs.get("piper_model_path"):
        params["model_path"] = kwargs["piper_model_path"]
    return PiperEngine(**params)


def _make_kokoro(kwargs: dict) -> KokoroEngine:
    params = {}
    if kwargs.get("kokoro_model_path"):
        params["model_path"] = kwargs["kokoro_model_path"]
    if kwargs.get("kokoro_voices_path"):
        params["voices_path"] = kwargs["kokoro_voices_path"]
    if kwargs.get("kokoro_voice"):
        params["voice"] = kwargs["kokoro_voice"]
    if kwargs.get("kokoro_lang"):
        params["lang"] = kwargs["kokoro_lang"]
    return KokoroEngine(**params)


def _make_ia(kwargs: dict) -> AITTSEngine:
    params = {}
    if kwargs.get("ia_model_name"):
        params["model_name"] = kwargs["ia_model_name"]
    if kwargs.get("ia_speaker_wav"):
        params["speaker_wav"] = kwargs["ia_speaker_wav"]
    return AITTSEngine(**params)


def get_engine(choice: str = "automatico", **kwargs) -> TTSEngine:
    """
    Retorna uma instância de TTSEngine pronta para uso, de acordo com `choice`.

    kwargs aceitos (todos opcionais, com nomes exclusivos por motor):
      espeak_voice, espeak_speed_wpm
      piper_model_path
      kokoro_model_path, kokoro_voices_path, kokoro_voice, kokoro_lang
      ia_model_name, ia_speaker_wav
    """
    if choice not in ENGINE_CHOICES:
        raise ValueError(f"Motor inválido: {choice!r}. Use um de {ENGINE_CHOICES}")

    if choice == "offline":
        return _make_espeak(kwargs)
    if choice == "piper":
        return _make_piper(kwargs)
    if choice == "kokoro":
        return _make_kokoro(kwargs)
    if choice == "ia":
        return _make_ia(kwargs)

    # automático: tenta do melhor pro mais garantido
    candidates = [
        _make_ia(kwargs),
        _make_kokoro(kwargs),
        _make_piper(kwargs),
        _make_espeak(kwargs),
    ]
    for engine in candidates:
        if engine.is_available():
            logger.info("Motor automático selecionado: %s", engine.name)
            return engine

    # Nenhum motor disponível de verdade — devolve espeak mesmo assim,
    # para a mensagem de erro final ser clara e acionável pro usuário.
    logger.warning("Nenhum motor de TTS disponível — verifique a instalação.")
    return candidates[-1]
