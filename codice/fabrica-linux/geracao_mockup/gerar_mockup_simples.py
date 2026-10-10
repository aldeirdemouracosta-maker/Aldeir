#!/usr/bin/env python3
"""Gera um mockup simples e automático (wireframe genérico), sem IA e sem
GPU — só desenho programático via QPainter. Serve como ponto de partida
rascunhado quando ainda não existe nenhuma imagem de mockup: desenha uma
barra de título e uma lista de elementos de interface (campos, botões,
listas) como retângulos rotulados, prontos para "Descrever mockup…"
interpretar depois.

Uso:
    python3 -m geracao_mockup.gerar_mockup_simples --saida /tmp/mockup.png \
        --titulo "Tela de login" --elemento "Campo usuário" --elemento "Botão Entrar"
"""

import argparse
import json
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen
from PySide6.QtWidgets import QApplication

ELEMENTOS_PADRAO = ["Campo de texto", "Botão OK", "Botão Cancelar", "Lista de itens"]


def _garantir_aplicacao_qt() -> None:
    """QPainter/QFont exigem uma aplicação Qt instanciada para carregar
    fontes — se a interface já estiver aberta, reaproveita a existente.
    Usa QApplication (não QGuiApplication): criar os dois tipos no mesmo
    processo derruba o Qt (visto na prática rodando os testes juntos)."""
    if QApplication.instance() is None:
        QApplication([])


def caminho_layout_json(caminho_imagem: Path) -> Path:
    """Onde o JSON de geometria de um mockup gerado por
    `gerar_mockup_simples` fica salvo — mesmo diretório e nome-base do
    PNG, extensão `.json`."""
    return caminho_imagem.with_suffix(".json")


def gerar_mockup_simples(
    caminho_saida: Path,
    titulo: str = "Tela sem título",
    elementos: Optional[List[str]] = None,
    largura: int = 900,
    altura: int = 600,
) -> Path:
    """Desenha um wireframe genérico (retângulos rotulados) e salva como
    PNG em `caminho_saida`. Não usa nenhum modelo de IA — é só um
    esqueleto estrutural, instantâneo, sem custo de VRAM.

    Salva também um JSON (`caminho_layout_json`) com a posição/tamanho
    exatos de cada elemento — a mesma geometria usada para desenhar, que
    senão seria descartada ao virar só um PNG. Um agente que for gerar a
    interface de verdade a partir daqui tem coordenadas determinísticas
    em vez de precisar adivinhar posição a partir de uma descrição em
    texto livre de um modelo de visão."""
    elementos = elementos or ELEMENTOS_PADRAO
    _garantir_aplicacao_qt()

    imagem = QImage(largura, altura, QImage.Format_RGB32)
    imagem.fill(QColor("white"))

    layout_elementos = []

    pintor = QPainter(imagem)
    try:
        pintor.setPen(QPen(QColor("#333333"), 2))
        pintor.drawRect(4, 4, largura - 8, altura - 8)

        altura_barra = 48
        pintor.fillRect(4, 4, largura - 8, altura_barra, QColor("#2f3640"))
        pintor.setPen(QColor("white"))
        pintor.setFont(QFont("Sans", 14, QFont.Bold))
        pintor.drawText(
            QRect(16, 4, largura - 32, altura_barra), Qt.AlignVCenter | Qt.AlignLeft, titulo
        )

        margem = 24
        espacamento = 16
        topo = altura_barra + 4 + margem
        altura_disponivel = altura - topo - margem
        altura_item = max(32, min(64, (altura_disponivel - espacamento * (len(elementos) - 1)) // len(elementos)))

        pintor.setFont(QFont("Sans", 11))
        y = topo
        for rotulo in elementos:
            pintor.setPen(QPen(QColor("#718093"), 2))
            pintor.setBrush(QColor("#f5f6fa"))
            pintor.drawRoundedRect(margem, y, largura - margem * 2, altura_item, 6, 6)
            pintor.setPen(QColor("#2f3640"))
            pintor.drawText(QRect(margem, y, largura - margem * 2, altura_item), Qt.AlignCenter, rotulo)
            layout_elementos.append(
                {"rotulo": rotulo, "x": margem, "y": y, "largura": largura - margem * 2, "altura": altura_item}
            )
            y += altura_item + espacamento
    finally:
        pintor.end()

    caminho_saida.parent.mkdir(parents=True, exist_ok=True)
    imagem.save(str(caminho_saida), "PNG")

    layout = {
        "titulo": titulo,
        "largura": largura,
        "altura": altura,
        "elementos": layout_elementos,
    }
    caminho_layout_json(caminho_saida).write_text(json.dumps(layout, ensure_ascii=False, indent=2))

    return caminho_saida


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--saida", type=Path, required=True, help="Caminho do PNG a gerar")
    parser.add_argument("--titulo", type=str, default="Tela sem título")
    parser.add_argument(
        "--elemento", action="append", dest="elementos", help="Rótulo de um elemento — repita a cada um"
    )
    parser.add_argument("--largura", type=int, default=900)
    parser.add_argument("--altura", type=int, default=600)
    args = parser.parse_args()

    caminho = gerar_mockup_simples(
        args.saida, titulo=args.titulo, elementos=args.elementos, largura=args.largura, altura=args.altura
    )
    print(caminho)


if __name__ == "__main__":
    main()
