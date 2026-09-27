"""
Testes ponta a ponta do IAVOX PDF Audio.

Requer que tests/sample.pdf e tests/scanned.pdf já existam (gerados por
make_sample_pdf.py) e, para os testes de IA, que o fake_ollama.py esteja
rodando em localhost:11434.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from iavox_pdf_audio.core.extractor import PDFExtractor
from iavox_pdf_audio.core.reader import IAVOXPDFReader, ReadingOptions
from iavox_pdf_audio.tts.espeak_engine import EspeakEngine
from iavox_pdf_audio.tts.selector import get_engine

SAMPLE_PDF = Path(__file__).parent / "sample.pdf"
SCANNED_PDF = Path(__file__).parent / "scanned.pdf"


def test_extractor_reads_text_and_image():
    extractor = PDFExtractor()
    result = extractor.extract(SAMPLE_PDF)
    assert result.total_pages == 2
    assert "Acessibilidade" in result.full_text
    assert len(result.all_images) == 1
    assert not result.used_ocr_anywhere


def test_extractor_falls_back_to_ocr():
    extractor = PDFExtractor(ocr_lang="por")
    result = extractor.extract(SCANNED_PDF)
    assert result.used_ocr_anywhere
    assert "escaneado" in result.full_text.lower() or "IAVOX" in result.full_text


def test_espeak_engine_generates_real_audio(tmp_path):
    engine = EspeakEngine()
    assert engine.is_available()
    out = engine.synthesize_to_file("teste do IAVOX", tmp_path / "out.wav")
    assert out.exists()
    assert out.stat().st_size > 0


def test_kokoro_engine_generates_real_audio_if_models_present(tmp_path):
    from iavox_pdf_audio.tts.kokoro_engine import KokoroEngine

    engine = KokoroEngine()
    if not engine.is_available():
        pytest.skip("Modelos do Kokoro não baixados neste ambiente de teste.")
    out = engine.synthesize_to_file("Teste de voz em português do Kokoro.", tmp_path / "kokoro.wav")
    assert out.exists()
    assert out.stat().st_size > 1000


def test_selector_automatico_falls_back_gracefully():
    engine = get_engine("automatico")
    assert engine.is_available()  # deve sempre achar pelo menos o espeak-ng


def test_reader_full_mode_end_to_end(tmp_path):
    reader = IAVOXPDFReader()
    options = ReadingOptions(
        mode="completo", describe_images=True, tts_choice="offline",
        save_audio=True, output_dir=tmp_path,
    )
    script = reader.build_script(SAMPLE_PDF, options)
    assert script.pages_count == 2
    assert script.image_descriptions_count == 1
    assert len(script.full_text) > 50

    audio_path = reader.synthesize(script, options)
    assert audio_path.exists()
    assert audio_path.stat().st_size > 0


def test_reader_summary_mode_all_densities():
    reader = IAVOXPDFReader()
    for density in ("curto", "medio", "detalhado"):
        options = ReadingOptions(mode="resumo", density=density, describe_images=False, save_audio=False)
        script = reader.build_script(SAMPLE_PDF, options)
        assert len(script.full_text) > 0


def test_invalid_mode_raises():
    reader = IAVOXPDFReader()
    with pytest.raises(ValueError):
        reader.build_script(SAMPLE_PDF, ReadingOptions(mode="invalido"))


def test_invalid_density_raises():
    reader = IAVOXPDFReader()
    with pytest.raises(ValueError):
        reader.build_script(SAMPLE_PDF, ReadingOptions(mode="resumo", density="invalido"))
