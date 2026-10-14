import asyncio
import sys
import zipfile
from pathlib import Path

import pytest

pytest.importorskip("pypdf")
pytest.importorskip("mammoth")

from pypdf import PdfWriter  # noqa: E402

from app.config import Settings  # noqa: E402
from app.core.models import UnavailableError  # noqa: E402
from app.main import build_service  # noqa: E402
from app.multimodal import convert  # noqa: E402
from app.multimodal.convert import ConvertError, convert_to_text  # noqa: E402
from app.multimodal.documents import DocumentIndex  # noqa: E402
from tests.test_multimodal import EmbProvider  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures"      # arquivos REAIS (reportlab / python-docx)


def run(c):
    return asyncio.run(c)


def test_real_pdf_keeps_accents_and_marks_pages():
    t = convert_to_text(FIX / "real.pdf")
    assert "[página 1]" in t and "[página 2]" in t
    assert "Relatório de gatos" in t and "ação e coração" in t and "Capítulo 2: carros" in t
    assert t.index("[página 1]") < t.index("gato") < t.index("[página 2]") < t.index("carros")


def test_real_docx_text_and_known_table_limitation():
    t = convert_to_text(FIX / "real.docx")
    assert "Manual de gatos" in t and "O gato é um felino doméstico. Não gosta de água." in t
    assert "Siamês" in t and "4 kg" in t        # o conteúdo da tabela vem, mas sem estrutura de linha/coluna


def test_scanned_pdf_has_no_text_and_points_to_ocr(tmp_path):
    w = PdfWriter(); w.add_blank_page(200, 200)
    p = tmp_path / "scan.pdf"
    w.write(p)
    with pytest.raises(ConvertError, match="ocr"):
        convert_to_text(p)


def test_hostile_pdfs(tmp_path):
    enc = tmp_path / "enc.pdf"
    w = PdfWriter(); w.add_blank_page(100, 100)
    w.encrypt("segredo", algorithm="RC4-128")          # AES exigiria a biblioteca 'cryptography' só para gravar
    w.write(enc)
    with pytest.raises(ConvertError, match="senha"):
        convert_to_text(enc)
    fake = tmp_path / "fake.pdf"
    fake.write_bytes(b"MZ\x90\x00 isto e um executavel")
    with pytest.raises(ConvertError, match="não é um PDF"):
        convert_to_text(fake)
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"%PDF-1.4\n1 0 obj <<garbage>> \nendobj\n" * 3)
    with pytest.raises(ConvertError, match="ilegível|sem texto"):
        convert_to_text(broken)


def test_hostile_docx(tmp_path):
    notdocx = tmp_path / "x.docx"
    notdocx.write_bytes(b"nao e zip")
    with pytest.raises(ConvertError, match="ilegível"):
        convert_to_text(notdocx)
    plainzip = tmp_path / "z.docx"
    with zipfile.ZipFile(plainzip, "w") as z:
        z.writestr("qualquer.txt", "oi")
    with pytest.raises(ConvertError, match="DOCX válido"):
        convert_to_text(plainzip)
    bomb = tmp_path / "bomb.docx"                      # ~100 KB compactado, > 100 MB descompactado
    with zipfile.ZipFile(bomb, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("word/document.xml", "<w:document/>")
        z.writestr("word/lixo.bin", b"\0" * (convert.MAX_UNZIPPED + 1))
    assert bomb.stat().st_size < 1_000_000
    with pytest.raises(ConvertError, match="grande demais"):
        convert_to_text(bomb)


def test_size_limit_and_unsupported_extension(tmp_path, monkeypatch):
    monkeypatch.setattr(convert, "MAX_DOC_BYTES", 100)
    with pytest.raises(ConvertError, match="limite"):
        convert_to_text(FIX / "real.docx")
    monkeypatch.undo()
    odt = tmp_path / "a.odt"
    odt.write_bytes(b"x")
    with pytest.raises(ConvertError, match="não suportado"):
        convert_to_text(odt)


def test_missing_libs_give_install_hint(monkeypatch):
    monkeypatch.setitem(sys.modules, "pypdf", None)     # força ImportError
    monkeypatch.setitem(sys.modules, "mammoth", None)
    for f in ("real.pdf", "real.docx"):
        with pytest.raises(UnavailableError, match=r"\.\[docs\]"):
            convert_to_text(FIX / f)


# ---------- integração com o RAG ----------
def svc(tmp_path):
    return build_service(Settings(media_dir=tmp_path / "media"), EmbProvider(), None, None, None, DocumentIndex())


def test_rag_indexes_pdf_docx_and_text_together_and_cites_pages(tmp_path):
    s = svc(tmp_path)
    d = s.assets.root / "docs"
    d.mkdir()
    for f in ("real.pdf", "real.docx"):
        (d / f).write_bytes((FIX / f).read_bytes())
    (d / "nota.md").write_text("Anotação solta sobre carros e motores.\n", encoding="utf-8")
    r = run(s.index_path("docs"))
    assert r["files"] == 3 and r["skipped"] == [] and r["documents"] == 3
    top = run(s.search("o gato felino que dorme", 3))
    assert {h["path"] for h in top[:2]} == {"docs/real.pdf", "docs/real.docx"}      # os dois documentos sobre gato
    pdf_hit = next(h for h in top if h["path"] == "docs/real.pdf")
    assert "[página 1]" in pdf_hit["text"]                                           # referência de página no trecho
    assert run(s.index_path("docs"))["new_chunks"] == 0                              # reindexar sem mudança: nada novo


def test_directory_skips_bad_documents_but_direct_request_errors(tmp_path):
    s = svc(tmp_path)
    d = s.assets.root / "docs"
    d.mkdir()
    (d / "ok.docx").write_bytes((FIX / "real.docx").read_bytes())
    (d / "ruim.pdf").write_bytes(b"MZ nao e pdf")
    r = run(s.index_path("docs"))
    assert r["files"] == 1 and len(r["skipped"]) == 1 and "ruim.pdf" in r["skipped"][0]
    with pytest.raises(ConvertError):
        run(s.index_path("docs/ruim.pdf"))


def test_rag_without_libs_reports_missing_dependency(tmp_path, monkeypatch):
    s = svc(tmp_path)
    (s.assets.root / "a.pdf").write_bytes((FIX / "real.pdf").read_bytes())
    monkeypatch.setitem(sys.modules, "pypdf", None)
    with pytest.raises(UnavailableError):
        run(s.index_path("a.pdf"))
    r = run(s.index_path("."))                           # em pasta: ignora e relata, não derruba a indexação
    assert r["files"] == 0 and "a.pdf" in r["skipped"][0]


def test_symlinked_document_is_refused(tmp_path):
    from tests.helpers import symlink
    s = svc(tmp_path)
    outside = tmp_path / "fora.pdf"
    outside.write_bytes((FIX / "real.pdf").read_bytes())
    symlink(outside, s.assets.root / "l.pdf")
    with pytest.raises(Exception, match="symlink"):
        run(s.index_path("l.pdf"))


def test_rag_agent_warns_when_index_gets_slow(tmp_path, monkeypatch):
    from app.agents import rag as ragmod
    from app.agents.rag import RagAgent
    s = svc(tmp_path)
    (s.assets.root / "a.md").write_text("O gato dorme.\n" * 1)
    monkeypatch.setattr(ragmod, "SLOW_CHUNKS", 0)
    out = run(RagAgent(s).run("rag_index", {"path": "a.md"}))
    assert "AVISO" in out and "sqlite-vec" in out
    monkeypatch.setattr(ragmod, "SLOW_CHUNKS", 5_000)
    assert "AVISO" not in run(RagAgent(s).run("rag_index", {"path": "a.md"}))
