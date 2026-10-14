"""Backends opcionais de inferência. Importam dependências só quando usados.

IMPORTANTE: os backends reais (SmolVLM, Whisper, Kokoro) NÃO foram executados nesta reconstrução:
não havia pesos nem pacotes instalados. Eles seguem a documentação das bibliotecas e precisam
de validação real. O restante do sistema é testado com backends simulados.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from typing import Protocol, Sequence

from app.core.models import UnavailableError


def _missing(modules: Sequence[str]) -> list[str]:
    return [m for m in modules if importlib.util.find_spec(m) is None]


class VisionBackend(Protocol):
    def probe(self) -> tuple[bool, str]: ...
    def describe(self, image: Path, prompt: str) -> str: ...


class SpeechBackend(Protocol):
    def probe(self) -> tuple[bool, str]: ...
    def transcribe(self, audio: Path) -> tuple[str, str]: ...  # (texto, idioma)


class VoiceBackend(Protocol):
    def probe(self) -> tuple[bool, str]: ...
    def voices(self) -> list[str]: ...
    def synthesize(self, text: str, voice: str) -> tuple[Sequence[float], int]: ...


class OcrBackend(Protocol):
    def probe(self) -> tuple[bool, str]: ...
    def read(self, image: Path) -> list[str]: ...


class ClipBackend(Protocol):
    """Embeddings imagem/texto no MESMO espaço vetorial (normalizados)."""
    def probe(self) -> tuple[bool, str]: ...
    def embed_image(self, image: Path) -> list[float]: ...
    def embed_text(self, text: str) -> list[float]: ...


class SmolVLMBackend:
    """SmolVLM 256M via transformers. Requer: transformers, torch, PIL e SWARM_VISION_MODEL (pasta local)."""

    def __init__(self, model_dir: str | None = None) -> None:
        self.model_dir = model_dir or os.environ.get("SWARM_VISION_MODEL", "")
        self._loaded = None

    def probe(self) -> tuple[bool, str]:
        miss = _missing(["transformers", "torch", "PIL"])
        if miss:
            return False, f"dependências ausentes: {', '.join(miss)}"
        if not self.model_dir or not Path(self.model_dir).is_dir():
            return False, "pesos ausentes (defina SWARM_VISION_MODEL)"
        return True, "ok"

    def describe(self, image: Path, prompt: str) -> str:
        ok, why = self.probe()
        if not ok:
            raise UnavailableError(why)
        from PIL import Image
        from transformers import AutoModelForVision2Seq, AutoProcessor
        if self._loaded is None:
            self._loaded = (AutoProcessor.from_pretrained(self.model_dir, local_files_only=True),
                            AutoModelForVision2Seq.from_pretrained(self.model_dir, local_files_only=True))
        proc, model = self._loaded
        msgs = [{"role": "user", "content": [{"type": "image"}, {"type": "text", "text": prompt}]}]
        text = proc.apply_chat_template(msgs, add_generation_prompt=True)
        inputs = proc(text=text, images=[Image.open(image).convert("RGB")], return_tensors="pt")
        out = model.generate(**inputs, max_new_tokens=200)
        return proc.batch_decode(out, skip_special_tokens=True)[0]


class WhisperBackend:
    """Whisper Tiny via faster-whisper. Requer o pacote e SWARM_SPEECH_MODEL (pasta local do modelo)."""

    def __init__(self, model_dir: str | None = None) -> None:
        self.model_dir = model_dir or os.environ.get("SWARM_SPEECH_MODEL", "")
        self._model = None

    def probe(self) -> tuple[bool, str]:
        miss = _missing(["faster_whisper"])
        if miss:
            return False, "dependências ausentes: faster-whisper"
        if not self.model_dir or not Path(self.model_dir).is_dir():
            return False, "pesos ausentes (defina SWARM_SPEECH_MODEL)"
        return True, "ok"

    def transcribe(self, audio: Path) -> tuple[str, str]:
        ok, why = self.probe()
        if not ok:
            raise UnavailableError(why)
        from faster_whisper import WhisperModel
        if self._model is None:
            self._model = WhisperModel(self.model_dir, device="cpu", compute_type="int8", local_files_only=True)
        segments, info = self._model.transcribe(str(audio))
        return " ".join(s.text.strip() for s in segments), info.language


class KokoroBackend:
    """Kokoro ONNX. Requer kokoro-onnx, SWARM_VOICE_MODEL (.onnx) e SWARM_VOICE_VOICES (voices.bin)."""

    def __init__(self, model: str | None = None, voices: str | None = None) -> None:
        self.model = model or os.environ.get("SWARM_VOICE_MODEL", "")
        self.voices_file = voices or os.environ.get("SWARM_VOICE_VOICES", "")
        self._k = None

    def probe(self) -> tuple[bool, str]:
        if _missing(["kokoro_onnx"]):
            return False, "dependências ausentes: kokoro-onnx"
        if not (Path(self.model).is_file() and Path(self.voices_file).is_file()):
            return False, "pesos ausentes (SWARM_VOICE_MODEL / SWARM_VOICE_VOICES)"
        return True, "ok"

    def _kokoro(self):
        ok, why = self.probe()
        if not ok:
            raise UnavailableError(why)
        if self._k is None:
            from kokoro_onnx import Kokoro
            self._k = Kokoro(self.model, self.voices_file)
        return self._k

    def voices(self) -> list[str]:
        return sorted(self._kokoro().get_voices())

    def synthesize(self, text: str, voice: str) -> tuple[Sequence[float], int]:
        samples, rate = self._kokoro().create(text, voice=voice, speed=1.0, lang="en-us")
        return samples.tolist(), int(rate)


class PaddleOcrBackend:
    """PP-OCR via PaddleOCR. Requer paddleocr + SWARM_OCR_DET e SWARM_OCR_REC (pastas locais dos modelos).

    Sem as pastas o PaddleOCR baixaria pesos sozinho; por isso o backend se declara indisponível."""

    def __init__(self, det_dir: str | None = None, rec_dir: str | None = None) -> None:
        self.det = det_dir or os.environ.get("SWARM_OCR_DET", "")
        self.rec = rec_dir or os.environ.get("SWARM_OCR_REC", "")
        self._ocr = None

    def probe(self) -> tuple[bool, str]:
        if _missing(["paddleocr"]):
            return False, "dependências ausentes: paddleocr"
        if not (Path(self.det).is_dir() and Path(self.rec).is_dir()):
            return False, "pesos ausentes (SWARM_OCR_DET / SWARM_OCR_REC)"
        return True, "ok"

    def read(self, image: Path) -> list[str]:
        ok, why = self.probe()
        if not ok:
            raise UnavailableError(why)
        from paddleocr import PaddleOCR
        if self._ocr is None:
            self._ocr = PaddleOCR(text_detection_model_dir=self.det, text_recognition_model_dir=self.rec,
                                  use_doc_orientation_classify=False, use_doc_unwarping=False)
        lines: list[str] = []
        for page in self._ocr.predict(str(image)):  # API 3.x: dict com 'rec_texts'
            lines += [t for t in page["rec_texts"] if t.strip()]
        return lines


class ChineseClipBackend:
    """Chinese-CLIP ViT-B/16 via transformers. Requer transformers, torch, PIL e SWARM_CLIP_MODEL (pasta local)."""

    def __init__(self, model_dir: str | None = None) -> None:
        self.model_dir = model_dir or os.environ.get("SWARM_CLIP_MODEL", "")
        self._m = None

    def probe(self) -> tuple[bool, str]:
        miss = _missing(["transformers", "torch", "PIL"])
        if miss:
            return False, f"dependências ausentes: {', '.join(miss)}"
        if not self.model_dir or not Path(self.model_dir).is_dir():
            return False, "pesos ausentes (defina SWARM_CLIP_MODEL)"
        return True, "ok"

    def _load(self):
        ok, why = self.probe()
        if not ok:
            raise UnavailableError(why)
        if self._m is None:
            from transformers import ChineseCLIPModel, ChineseCLIPProcessor
            self._m = (ChineseCLIPProcessor.from_pretrained(self.model_dir, local_files_only=True),
                       ChineseCLIPModel.from_pretrained(self.model_dir, local_files_only=True))
        return self._m

    @staticmethod
    def _norm(t) -> list[float]:
        return (t / t.norm(dim=-1, keepdim=True))[0].tolist()

    def embed_image(self, image: Path) -> list[float]:
        from PIL import Image
        proc, model = self._load()
        return self._norm(model.get_image_features(**proc(images=Image.open(image).convert("RGB"), return_tensors="pt")))

    def embed_text(self, text: str) -> list[float]:
        proc, model = self._load()
        return self._norm(model.get_text_features(**proc(text=[text], padding=True, return_tensors="pt")))
