"""
IAVOX PDF Reader
=================
Orquestra o fluxo completo:

  PDF -> extrai texto (+ OCR se precisar) e imagens
      -> (opcional) resume/reescreve o texto por densidade
      -> (opcional) gera audiodescrição de cada imagem via IA
      -> monta o roteiro final de leitura (texto + descrições intercaladas)
      -> sintetiza em áudio (arquivo) e/ou lê ao vivo

Este é o módulo que a interface do IAVOX (CLI, ou futura tela) deve chamar.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from ..tts.base import TTSEngine
from ..tts.selector import get_engine
from .extractor import ExtractionResult, PDFExtractor
from .image_description import ImageDescriber
from .summarizer import VALID_DENSITIES, TextSummarizer

logger = logging.getLogger("iavox.reader")


@dataclass
class ReadingOptions:
    mode: str = "completo"          # "completo" ou "resumo"
    density: str = "medio"          # curto | medio | detalhado (só usado se mode="resumo")
    describe_images: bool = True    # gerar audiodescrição das imagens do PDF
    tts_choice: str = "automatico"  # offline | piper | ia | automatico
    ocr_lang: str = "por"
    save_audio: bool = True
    output_dir: str | Path = "./iavox_saida"
    piper_model_path: str | None = None  # caminho do modelo .onnx do Piper (Windows/Linux)
    kokoro_model_path: str | None = None
    kokoro_voices_path: str | None = None
    espeak_binary_path: str | None = None  # caminho manual do espeak-ng.exe (Windows)


@dataclass
class ReadingScript:
    """Roteiro final, pronto para ser sintetizado em voz — texto puro em pt-BR."""
    full_text: str
    used_ocr: bool
    image_descriptions_count: int
    pages_count: int


class IAVOXPDFReader:
    """
    Uso básico:
        reader = IAVOXPDFReader()
        script = reader.build_script("documento.pdf", ReadingOptions(mode="resumo", density="curto"))
        audio_path = reader.synthesize(script, ReadingOptions())
    """

    def __init__(self):
        self.extractor = PDFExtractor()
        self.summarizer = TextSummarizer()
        self.describer = ImageDescriber()

    # ---------------------------------------------------------------- texto

    def build_script(
        self, pdf_path: str | Path, options: ReadingOptions, progress_cb=None
    ) -> ReadingScript:
        if options.mode not in ("completo", "resumo"):
            raise ValueError("mode deve ser 'completo' ou 'resumo'")
        if options.density not in VALID_DENSITIES:
            raise ValueError(f"density deve ser uma de {VALID_DENSITIES}")

        self.extractor.ocr_lang = options.ocr_lang
        self.extractor.extract_images = options.describe_images

        extraction: ExtractionResult = self.extractor.extract(pdf_path, progress_cb=progress_cb)

        pieces: list[str] = []
        image_desc_count = 0

        for page in extraction.pages:
            page_text = page.text.strip()

            if options.mode == "resumo" and page_text:
                if self.summarizer.is_available():
                    page_text = self.summarizer.summarize(page_text, density=options.density)
                else:
                    logger.info(
                        "IA de resumo indisponível — página %s lida na íntegra.",
                        page.page_number,
                    )

            if page_text:
                pieces.append(f"Página {page.page_number}. {page_text}")

            if options.describe_images and page.images:
                image_available = self.describer.is_available()
                for img in page.images:
                    if image_available:
                        desc = self.describer.describe(img.image_bytes)
                    else:
                        desc = self.describer._fallback_description()  # type: ignore[attr-defined]
                    pieces.append(f"Imagem na página {page.page_number}: {desc}")
                    image_desc_count += 1

        full_text = "\n\n".join(pieces).strip()

        return ReadingScript(
            full_text=full_text,
            used_ocr=extraction.used_ocr_anywhere,
            image_descriptions_count=image_desc_count,
            pages_count=extraction.total_pages,
        )

    # ---------------------------------------------------------------- áudio

    def synthesize(self, script: ReadingScript, options: ReadingOptions) -> Path | None:
        """Gera o arquivo de áudio final do roteiro. Retorna None se save_audio=False."""
        if not options.save_audio:
            return None

        engine = get_engine(
            options.tts_choice,
            piper_model_path=options.piper_model_path,
            kokoro_model_path=options.kokoro_model_path,
            kokoro_voices_path=options.kokoro_voices_path,
            espeak_binary_path=options.espeak_binary_path,
        )
        if not engine.is_available():
            raise RuntimeError(
                f"Motor de TTS '{options.tts_choice}' (resolvido para {engine.name}) "
                "não está disponível neste sistema. Verifique a instalação."
            )

        output_dir = Path(options.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "leitura.wav"

        logger.info("Sintetizando áudio com motor: %s", engine.name)
        return engine.synthesize_to_file(script.full_text, output_path)

    def speak_live(self, script: ReadingScript, options: ReadingOptions, engine: TTSEngine | None = None) -> None:
        """Lê o roteiro em voz alta diretamente (sem salvar arquivo), quando o motor suportar."""
        engine = engine or get_engine(
            options.tts_choice,
            piper_model_path=options.piper_model_path,
            kokoro_model_path=options.kokoro_model_path,
            kokoro_voices_path=options.kokoro_voices_path,
            espeak_binary_path=options.espeak_binary_path,
        )
        if not engine.is_available():
            raise RuntimeError(f"Motor de TTS '{engine.name}' não está disponível.")
        engine.speak(script.full_text)
