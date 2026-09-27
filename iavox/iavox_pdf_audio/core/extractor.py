"""
IAVOX PDF Extractor
====================
Extrai texto e imagens de um PDF, com fallback para OCR (Tesseract, pt-BR)
quando o PDF for escaneado / não tiver camada de texto.

Sem dependência de nuvem: tudo roda local usando pypdf/pdfplumber para texto
e pdf2image + pytesseract para OCR quando necessário.
"""
from __future__ import annotations

import io
import logging
import platform
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber
import pypdf
from PIL import Image

logger = logging.getLogger("iavox.extractor")

# OCR e conversão de página em imagem são opcionais em tempo de import,
# para não quebrar o pacote em ambientes sem essas libs/binários instalados.
try:
    import pytesseract
except ImportError:  # pragma: no cover
    pytesseract = None

try:
    from pdf2image import convert_from_path
except ImportError:  # pragma: no cover
    convert_from_path = None


@dataclass
class ExtractedImage:
    """Uma imagem encontrada dentro do PDF, pronta para audiodescrição."""
    page_number: int          # 1-indexed
    index_in_page: int        # ordem da imagem dentro da página
    image_bytes: bytes
    image_format: str = "png"
    width: int = 0
    height: int = 0


@dataclass
class ExtractedPage:
    page_number: int
    text: str
    used_ocr: bool = False
    images: list[ExtractedImage] = field(default_factory=list)


@dataclass
class ExtractionResult:
    source_path: str
    pages: list[ExtractedPage] = field(default_factory=list)
    total_pages: int = 0

    @property
    def full_text(self) -> str:
        return "\n\n".join(p.text.strip() for p in self.pages if p.text.strip())

    @property
    def used_ocr_anywhere(self) -> bool:
        return any(p.used_ocr for p in self.pages)

    @property
    def all_images(self) -> list[ExtractedImage]:
        imgs = []
        for p in self.pages:
            imgs.extend(p.images)
        return imgs


MIN_CHARS_BEFORE_OCR = 20  # se a página tiver menos texto "de verdade" que isso, tentamos OCR

# Caminhos padrão de instalação no Windows (instaladores oficiais costumam
# usar esses locais) — usados como fallback automático se o binário não
# estiver no PATH, para o usuário não precisar configurar nada manualmente.
WINDOWS_DEFAULT_TESSERACT_PATHS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
]


def _autodetect_tesseract_cmd() -> str | None:
    if platform.system() != "Windows":
        return None
    for candidate in WINDOWS_DEFAULT_TESSERACT_PATHS:
        if Path(candidate).exists():
            return candidate
    return None


class PDFExtractor:
    """
    Extrai texto e imagens de um PDF.

    Uso:
        extractor = PDFExtractor(ocr_lang="por")
        result = extractor.extract("documento.pdf")
        print(result.full_text)
    """

    def __init__(
        self,
        ocr_lang: str = "por",
        extract_images: bool = True,
        ocr_dpi: int = 200,
        tesseract_cmd: str | None = None,
        poppler_path: str | None = None,
    ):
        self.ocr_lang = ocr_lang
        self.extract_images = extract_images
        self.ocr_dpi = ocr_dpi
        # No Windows, tesseract.exe e poppler (pdftoppm.exe) geralmente não
        # ficam no PATH por padrão — permite apontar o caminho explicitamente.
        self.poppler_path = poppler_path
        if tesseract_cmd:
            resolved_tesseract = tesseract_cmd
        else:
            resolved_tesseract = _autodetect_tesseract_cmd()
        if resolved_tesseract and pytesseract is not None:
            pytesseract.pytesseract.tesseract_cmd = resolved_tesseract

    def extract(self, pdf_path: str | Path, progress_cb=None) -> ExtractionResult:
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF não encontrado: {pdf_path}")

        result = ExtractionResult(source_path=str(pdf_path))

        # Imagens são extraídas uma vez para o documento inteiro e depois
        # agrupadas por página, para reaproveitar o reader do pypdf.
        images_by_page: dict[int, list[ExtractedImage]] = {}
        if self.extract_images:
            for img in PDFImageExtractor().extract_all_images(pdf_path):
                images_by_page.setdefault(img.page_number, []).append(img)

        with pdfplumber.open(pdf_path) as pdf:
            result.total_pages = len(pdf.pages)
            for i, page in enumerate(pdf.pages, start=1):
                if progress_cb:
                    progress_cb(i, result.total_pages, "extraindo texto")

                raw_text = (page.extract_text() or "").strip()
                used_ocr = False

                if len(raw_text) < MIN_CHARS_BEFORE_OCR:
                    ocr_text = self._ocr_page(pdf_path, i)
                    if ocr_text:
                        raw_text = ocr_text
                        used_ocr = True

                result.pages.append(
                    ExtractedPage(
                        page_number=i,
                        text=raw_text,
                        used_ocr=used_ocr,
                        images=images_by_page.get(i, []),
                    )
                )

        return result

    def _ocr_page(self, pdf_path: Path, page_number: int) -> str:
        """Renderiza a página como imagem e roda OCR em português."""
        if pytesseract is None or convert_from_path is None:
            logger.warning(
                "OCR indisponível (pytesseract/pdf2image não instalados). "
                "Página %s ficará sem texto.", page_number
            )
            return ""
        try:
            images = convert_from_path(
                str(pdf_path), dpi=self.ocr_dpi,
                first_page=page_number, last_page=page_number,
                poppler_path=self.poppler_path,
            )
            if not images:
                return ""
            text = pytesseract.image_to_string(images[0], lang=self.ocr_lang)
            return text.strip()
        except Exception as exc:  # noqa: BLE001 - nunca deixar o OCR derrubar a extração
            logger.warning("Falha no OCR da página %s: %s", page_number, exc)
            return ""




class PDFImageExtractor:
    """
    Extrator dedicado de imagens embutidas em PDFs, usando pypdf.
    Mantido separado do PDFExtractor de texto para simplicidade e testabilidade.
    """

    def __init__(self, min_width: int = 60, min_height: int = 60):
        self.min_width = min_width
        self.min_height = min_height

    def extract_all_images(self, pdf_path: str | Path) -> list[ExtractedImage]:
        pdf_path = Path(pdf_path)
        reader = pypdf.PdfReader(str(pdf_path))
        results: list[ExtractedImage] = []

        for page_number, page in enumerate(reader.pages, start=1):
            try:
                image_objs = list(page.images)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Falha ao ler imagens da página %s: %s", page_number, exc)
                continue

            for idx, img in enumerate(image_objs):
                try:
                    pil_img = Image.open(io.BytesIO(img.data))
                    if pil_img.width < self.min_width or pil_img.height < self.min_height:
                        continue  # ignora ícones/decorações minúsculas, não valem audiodescrição
                    buf = io.BytesIO()
                    fmt = "PNG"
                    pil_img.convert("RGB").save(buf, format=fmt)
                    results.append(
                        ExtractedImage(
                            page_number=page_number,
                            index_in_page=idx,
                            image_bytes=buf.getvalue(),
                            image_format="png",
                            width=pil_img.width,
                            height=pil_img.height,
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "Falha ao processar imagem %s da página %s: %s", idx, page_number, exc
                    )
        return results
