"""Operações de PDF do LumePDF. Todas trabalham com arquivos em disco."""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image
from pypdf import PdfReader, PdfWriter
from reportlab.lib.colors import Color
from reportlab.pdfgen import canvas


class PdfError(ValueError):
    """Erro de uso (entrada inválida); a mensagem é mostrada ao usuário."""


def parse_ranges(spec: str, total: int) -> list[int]:
    """'1-3,5,8-' -> índices base 0, na ordem digitada. Vazio = todas."""
    spec = (spec or "").strip()
    if not spec:
        return list(range(total))
    pages: list[int] = []
    for part in spec.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            if "-" in part:
                a, b = part.split("-", 1)
                start = int(a) if a.strip() else 1
                end = int(b) if b.strip() else total
            else:
                start = end = int(part)
        except ValueError:
            raise PdfError(f"Intervalo inválido: '{part}'") from None
        if start < 1 or end > total or start > end:
            raise PdfError(f"Intervalo fora do documento (1-{total}): '{part}'")
        pages.extend(range(start - 1, end))
    if not pages:
        raise PdfError("Nenhuma página selecionada.")
    return pages


def _reader(path, password: str = "") -> PdfReader:
    reader = PdfReader(str(path))
    if reader.is_encrypted:
        if not reader.decrypt(password or ""):
            raise PdfError("PDF protegido por senha. Informe a senha correta.")
    return reader


def _save(writer: PdfWriter, out) -> Path:
    with open(out, "wb") as fh:
        writer.write(fh)
    return Path(out)


def page_count(path, password: str = "") -> int:
    return len(_reader(path, password).pages)


def info(path) -> dict:
    reader = PdfReader(str(path))
    encrypted = reader.is_encrypted
    if encrypted and not reader.decrypt(""):
        return {"pages": 0, "encrypted": True, "title": "", "author": ""}
    meta = reader.metadata or {}
    return {
        "pages": len(reader.pages),
        "encrypted": encrypted,
        "title": str(meta.get("/Title", "") or ""),
        "author": str(meta.get("/Author", "") or ""),
    }


def merge(paths, out) -> Path:
    if len(paths) < 2:
        raise PdfError("Selecione ao menos 2 PDFs para juntar.")
    writer = PdfWriter()
    for p in paths:
        writer.append(_reader(p))
    return _save(writer, out)


def extract_pages(path, spec: str, out, password: str = "") -> Path:
    reader = _reader(path, password)
    writer = PdfWriter()
    for i in parse_ranges(spec, len(reader.pages)):
        writer.add_page(reader.pages[i])
    return _save(writer, out)


def delete_pages(path, spec: str, out, password: str = "") -> Path:
    reader = _reader(path, password)
    total = len(reader.pages)
    if not (spec or "").strip():
        raise PdfError("Informe as páginas a excluir.")
    drop = set(parse_ranges(spec, total))
    keep = [i for i in range(total) if i not in drop]
    if not keep:
        raise PdfError("Não é possível excluir todas as páginas.")
    writer = PdfWriter()
    for i in keep:
        writer.add_page(reader.pages[i])
    return _save(writer, out)


def split(path, spec: str, out_zip, password: str = "") -> Path:
    """Sem intervalo: uma página por arquivo. Com intervalo ('1-3,5'): um arquivo por trecho."""
    reader = _reader(path, password)
    total = len(reader.pages)
    spec = (spec or "").strip()
    if spec:
        groups = [parse_ranges(p, total) for p in spec.replace(";", ",").split(",") if p.strip()]
    else:
        groups = [[i] for i in range(total)]
    stem = Path(path).stem
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for n, group in enumerate(groups, 1):
            writer = PdfWriter()
            for i in group:
                writer.add_page(reader.pages[i])
            buf = io.BytesIO()
            writer.write(buf)
            label = f"p{group[0] + 1}" if len(group) == 1 else f"p{group[0] + 1}-{group[-1] + 1}"
            zf.writestr(f"{stem}_{n:02d}_{label}.pdf", buf.getvalue())
    return Path(out_zip)


def rotate(path, angle: int, spec: str, out, password: str = "") -> Path:
    if angle not in (90, 180, 270, -90):
        raise PdfError("Ângulo deve ser 90, 180 ou 270.")
    reader = _reader(path, password)
    targets = set(parse_ranges(spec, len(reader.pages)))
    writer = PdfWriter()
    for i, page in enumerate(reader.pages):
        if i in targets:
            page.rotate(angle % 360)
        writer.add_page(page)
    return _save(writer, out)


def reorder(path, order: str, out, password: str = "") -> Path:
    """`order` lista a nova sequência, ex.: '3,1,2'. Páginas omitidas são removidas."""
    reader = _reader(path, password)
    writer = PdfWriter()
    for i in parse_ranges(order, len(reader.pages)):
        writer.add_page(reader.pages[i])
    return _save(writer, out)


def compress(path, level: str, out, password: str = "") -> Path:
    """'leve' = reotimiza streams; 'forte' = rasteriza em JPEG (perde texto selecionável)."""
    if level == "forte":
        return _compress_raster(path, out, password, dpi=110, quality=60)
    if level == "media":
        return _compress_raster(path, out, password, dpi=150, quality=75)
    reader = _reader(path, password)
    writer = PdfWriter(clone_from=reader)
    for page in writer.pages:
        page.compress_content_streams()
    writer.compress_identical_objects(remove_duplicates=True, remove_unreferenced=True)
    return _save(writer, out)


def _open_pdfium(path, password: str = ""):
    try:
        return pdfium.PdfDocument(str(path), password=password or None)
    except pdfium.PdfiumError as exc:
        raise PdfError("Não foi possível abrir o PDF (senha incorreta ou arquivo corrompido).") from exc


def _compress_raster(path, out, password: str, dpi: int, quality: int) -> Path:
    doc = _open_pdfium(path, password)
    images = []
    for page in doc:
        images.append(page.render(scale=dpi / 72).to_pil().convert("RGB"))
    if not images:
        raise PdfError("PDF sem páginas.")
    images[0].save(out, "PDF", resolution=dpi, save_all=True, append_images=images[1:], quality=quality)
    return Path(out)


def images_to_pdf(paths, out) -> Path:
    if not paths:
        raise PdfError("Selecione ao menos uma imagem.")
    pages = []
    for p in paths:
        try:
            img = Image.open(p)
            img.load()
        except OSError:
            raise PdfError(f"Imagem inválida: {Path(p).name}") from None
        if img.mode in ("RGBA", "LA", "P"):
            bg = Image.new("RGB", img.size, "white")
            rgba = img.convert("RGBA")
            bg.paste(rgba, mask=rgba.split()[-1])
            img = bg
        pages.append(img.convert("RGB"))
    pages[0].save(out, "PDF", resolution=150, save_all=True, append_images=pages[1:])
    return Path(out)


def pdf_to_images(path, fmt: str, dpi: int, spec: str, out_zip, password: str = "") -> Path:
    fmt = fmt.lower()
    if fmt not in ("png", "jpg"):
        raise PdfError("Formato deve ser png ou jpg.")
    dpi = max(36, min(int(dpi), 400))
    doc = _open_pdfium(path, password)
    stem = Path(path).stem
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for i in parse_ranges(spec, len(doc)):
            img = doc[i].render(scale=dpi / 72).to_pil()
            buf = io.BytesIO()
            if fmt == "jpg":
                img.convert("RGB").save(buf, "JPEG", quality=90)
            else:
                img.save(buf, "PNG")
            zf.writestr(f"{stem}_p{i + 1:03d}.{fmt}", buf.getvalue())
    return Path(out_zip)


def extract_text(path, out, password: str = "") -> Path:
    reader = _reader(path, password)
    parts = []
    for i, page in enumerate(reader.pages, 1):
        parts.append(f"--- Página {i} ---\n{(page.extract_text() or '').strip()}\n")
    Path(out).write_text("\n".join(parts), encoding="utf-8")
    return Path(out)


def watermark(path, text: str, out, password: str = "", opacity: float = 0.2, size: int = 60) -> Path:
    text = (text or "").strip()
    if not text:
        raise PdfError("Informe o texto da marca d'água.")
    reader = _reader(path, password)
    writer = PdfWriter()
    for page in reader.pages:
        w, h = float(page.mediabox.width), float(page.mediabox.height)
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=(w, h))
        c.setFillColor(Color(0.5, 0.5, 0.5, alpha=max(0.02, min(opacity, 1.0))))
        c.setFont("Helvetica-Bold", size)
        c.translate(w / 2, h / 2)
        c.rotate(45)
        c.drawCentredString(0, 0, text)
        c.save()
        buf.seek(0)
        out_page = writer.add_page(page)
        out_page.merge_page(PdfReader(buf).pages[0])
    return _save(writer, out)


def page_numbers(path, out, password: str = "") -> Path:
    reader = _reader(path, password)
    writer = PdfWriter()
    for n, page in enumerate(reader.pages, 1):
        w, h = float(page.mediabox.width), float(page.mediabox.height)
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=(w, h))
        c.setFont("Helvetica", 10)
        c.drawCentredString(w / 2, 20, f"{n} / {len(reader.pages)}")
        c.save()
        buf.seek(0)
        out_page = writer.add_page(page)
        out_page.merge_page(PdfReader(buf).pages[0])
    return _save(writer, out)


def protect(path, user_password: str, out) -> Path:
    if not user_password:
        raise PdfError("Informe a senha.")
    writer = PdfWriter(clone_from=_reader(path))
    writer.encrypt(user_password)
    return _save(writer, out)


def unlock(path, password: str, out) -> Path:
    reader = PdfReader(str(path))
    if reader.is_encrypted and not reader.decrypt(password or ""):
        raise PdfError("Senha incorreta.")
    writer = PdfWriter(clone_from=reader)
    return _save(writer, out)


def render_thumbnail(path, index: int, width: int = 180, password: str = "") -> bytes:
    doc = _open_pdfium(path, password)
    if not 0 <= index < len(doc):
        raise PdfError("Página inexistente.")
    page = doc[index]
    scale = width / float(page.get_width())
    buf = io.BytesIO()
    page.render(scale=scale).to_pil().convert("RGB").save(buf, "JPEG", quality=80)
    return buf.getvalue()
