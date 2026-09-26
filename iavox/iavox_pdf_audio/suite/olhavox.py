"""
OlhaVox (F3) e leitura de imagem/tela do LeitorVox (F1).

- ler_texto_imagem(): OCR em português de uma imagem ou captura de tela.
- descrever_imagem(): audiodescrição por IA de visão (Ollama/llava) +
  o texto que houver na imagem, juntos em uma fala só.
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from ..core.extractor import _autodetect_tesseract_cmd
from ..core.image_description import ImageDescriber

try:
    import pytesseract
except ImportError:  # pragma: no cover
    pytesseract = None


def _abrir(imagem: str | Path | bytes | Image.Image) -> Image.Image:
    if isinstance(imagem, Image.Image):
        return imagem
    if isinstance(imagem, (bytes, bytearray)):
        return Image.open(io.BytesIO(imagem))
    return Image.open(imagem)


def ler_texto_imagem(imagem, lang: str = "por", tesseract_cmd: str = "") -> str:
    """OCR da imagem. Retorna '' se não houver texto ou o OCR não estiver instalado."""
    if pytesseract is None:
        raise RuntimeError("OCR indisponível: instale pytesseract e o Tesseract com idioma português.")
    cmd = tesseract_cmd or _autodetect_tesseract_cmd()
    if cmd:
        pytesseract.pytesseract.tesseract_cmd = cmd
    img = _abrir(imagem).convert("RGB")
    # imagens pequenas (ícones, prints recortados) leem melhor ampliadas
    if img.width < 1000:
        fator = 1000 / img.width
        img = img.resize((1000, int(img.height * fator)))
    try:
        texto = pytesseract.image_to_string(img, lang=lang)
    except pytesseract.TesseractError:
        texto = pytesseract.image_to_string(img)  # sem o pacote de português
    return " ".join(texto.split())


@dataclass
class Descricao:
    descricao: str
    texto_na_imagem: str
    usou_ia: bool

    def como_fala(self) -> str:
        partes = [self.descricao]
        if self.texto_na_imagem:
            partes.append(f"Texto na imagem: {self.texto_na_imagem}")
        return " ".join(partes)


def descrever_imagem(imagem, describer: ImageDescriber | None = None, tesseract_cmd: str = "") -> Descricao:
    describer = describer or ImageDescriber()
    img = _abrir(imagem)
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG")

    try:
        texto = ler_texto_imagem(img, tesseract_cmd=tesseract_cmd)
    except Exception:  # noqa: BLE001 - OCR é complemento, não pode derrubar a descrição
        texto = ""

    if describer.is_available():
        return Descricao(describer.describe(buf.getvalue()), texto, usou_ia=True)

    largura, altura = img.size
    formato = "horizontal" if largura > altura else "vertical" if altura > largura else "quadrada"
    base = (
        f"Imagem {formato}, de {largura} por {altura} pixels. A descrição por IA não está "
        "disponível: instale o Ollama com o modelo llava para descrever o conteúdo visual."
    )
    return Descricao(base, texto, usou_ia=False)
