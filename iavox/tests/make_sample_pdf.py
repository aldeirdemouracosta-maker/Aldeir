"""Gera um PDF de teste com 2 páginas: texto + uma imagem embutida."""
from pathlib import Path

from PIL import Image, ImageDraw
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas

OUT = Path(__file__).parent / "sample.pdf"
IMG = Path(__file__).parent / "sample_chart.png"


def make_image():
    img = Image.new("RGB", (400, 250), "white")
    d = ImageDraw.Draw(img)
    d.rectangle([20, 20, 380, 230], outline="black", width=3)
    # "gráfico de barras" simples
    bars = [(60, 200, 100, 60, "blue"), (140, 200, 100, 120, "green"), (220, 200, 100, 90, "red")]
    for x0, y0, w, h, color in bars:
        d.rectangle([x0, y0 - h, x0 + w, y0], fill=color)
    d.text((30, 30), "Vendas por trimestre", fill="black")
    img.save(IMG)


def make_pdf():
    make_image()
    c = canvas.Canvas(str(OUT), pagesize=A4)

    # Página 1: texto puro
    c.setFont("Helvetica", 12)
    text = c.beginText(2 * cm, 27 * cm)
    text.textLines(
        "Relatório de Acessibilidade Educacional\n\n"
        "Este documento descreve as ferramentas desenvolvidas para apoiar "
        "estudantes com deficiência visual no ensino fundamental e médio.\n\n"
        "O projeto IAVOX integra o DOSVOX, leitor de tela amplamente usado "
        "no Brasil, com recursos de inteligência artificial para leitura de "
        "PDFs, geração de audiodescrição de imagens e resumo automático de "
        "textos longos, permitindo que o estudante escolha o nível de "
        "detalhe que deseja ouvir.\n\n"
        "A seguir, um gráfico ilustrando a evolução do uso da ferramenta "
        "ao longo dos três primeiros trimestres do projeto piloto."
    )
    c.drawText(text)
    c.showPage()

    # Página 2: imagem embutida
    c.drawImage(str(IMG), 2 * cm, 15 * cm, width=12 * cm, height=7.5 * cm)
    c.setFont("Helvetica", 12)
    c.drawString(2 * cm, 13 * cm, "Figura 1: gráfico de vendas trimestrais (exemplo).")
    c.showPage()

    c.save()
    print(f"PDF gerado em: {OUT}")


if __name__ == "__main__":
    make_pdf()
