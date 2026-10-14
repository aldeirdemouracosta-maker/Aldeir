"""Texto de PDF e DOCX para o RAG, com bibliotecas leves (pypdf ~puro Python, mammoth): 2,3 MB no total.

(MarkItDown foi testado e descartado: com PDF/DOCX trouxe 193 MB — numpy, onnxruntime, magika.)
Limites honestos: tabelas do DOCX perdem a estrutura de linhas; PDF escaneado não tem texto (use o agente ocr);
as referências do RAG apontam linhas do texto convertido — nos PDFs, cada página começa com "[página N]".
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

from app.core.models import SwarmError, UnavailableError

DOC_EXT = {".pdf", ".docx"}
MAX_DOC_BYTES = 20 * 2**20
MAX_PAGES = 500
MAX_TEXT_CHARS = 2_000_000
MAX_UNZIPPED = 100 * 2**20   # proteção contra "zip bomb" no DOCX
INSTALL_HINT = "instale as bibliotecas leves: pip install -e '.[docs]'"


class ConvertError(SwarmError):
    pass


def convert_to_text(path: Path) -> str:
    """Texto do documento. Bloqueante: chame em thread."""
    if path.stat().st_size > MAX_DOC_BYTES:
        raise ConvertError(f"documento acima do limite de {MAX_DOC_BYTES // 2**20} MB: {path.name}")
    kind = path.suffix.lower()
    text = _pdf(path) if kind == ".pdf" else _docx(path) if kind == ".docx" else None
    if text is None:
        raise ConvertError(f"formato não suportado: {kind}")
    if not text.strip():
        raise ConvertError(f"{path.name}: sem texto extraível (PDF escaneado? use o agente ocr)")
    return text[:MAX_TEXT_CHARS]


def _pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
        from pypdf.errors import DependencyError, PyPdfError
    except ImportError as e:
        raise UnavailableError(f"leitor de PDF ausente: {INSTALL_HINT}") from e
    with path.open("rb") as f:
        if f.read(5) != b"%PDF-":
            raise ConvertError(f"{path.name}: não é um PDF")
    try:
        reader = PdfReader(str(path))
        if reader.is_encrypted:
            raise ConvertError(f"{path.name}: PDF protegido por senha")
        if len(reader.pages) > MAX_PAGES:
            raise ConvertError(f"{path.name}: {len(reader.pages)} páginas (máximo {MAX_PAGES})")
        pages = [f"[página {n}]\n{(p.extract_text() or '').strip()}" for n, p in enumerate(reader.pages, 1)]
    except ConvertError:
        raise
    except DependencyError as e:  # ex.: PDF com AES e sem a biblioteca 'cryptography'
        raise ConvertError(f"{path.name}: PDF exige biblioteca adicional ({e})") from e
    except (PyPdfError, ValueError, KeyError, OSError, RecursionError) as e:
        raise ConvertError(f"{path.name}: PDF ilegível ({type(e).__name__})") from e
    return "\n\n".join(pages) if any(p.split("\n", 1)[1].strip() for p in pages) else ""


def _docx(path: Path) -> str:
    try:
        import mammoth
    except ImportError as e:
        raise UnavailableError(f"leitor de DOCX ausente: {INSTALL_HINT}") from e
    try:
        with zipfile.ZipFile(path) as z:
            if "word/document.xml" not in z.namelist():
                raise ConvertError(f"{path.name}: não é um DOCX válido")
            if sum(i.file_size for i in z.infolist()) > MAX_UNZIPPED:
                raise ConvertError(f"{path.name}: conteúdo descompactado grande demais")
        with path.open("rb") as f:
            return mammoth.extract_raw_text(io.BytesIO(f.read())).value
    except ConvertError:
        raise
    except (zipfile.BadZipFile, KeyError, ValueError, OSError) as e:
        raise ConvertError(f"{path.name}: DOCX ilegível ({type(e).__name__})") from e
