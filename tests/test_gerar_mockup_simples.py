"""Testes do gerador de mockup simples (wireframe programático, sem IA).
Roda sem tela real via QT_QPA_PLATFORM=offscreen — a variável precisa
estar definida antes de qualquer import do Qt."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtGui import QImage

import json

from geracao_mockup.gerar_mockup_simples import ELEMENTOS_PADRAO, caminho_layout_json, gerar_mockup_simples


def test_gerar_mockup_simples_cria_png_com_tamanho_pedido(tmp_path: Path):
    caminho = gerar_mockup_simples(tmp_path / "mockup.png", largura=400, altura=300)

    assert caminho == tmp_path / "mockup.png"
    assert caminho.is_file()
    imagem = QImage(str(caminho))
    assert imagem.width() == 400
    assert imagem.height() == 300


def test_gerar_mockup_simples_usa_elementos_padrao_quando_nao_informado(tmp_path: Path):
    caminho = gerar_mockup_simples(tmp_path / "mockup.png")

    assert caminho.is_file()
    assert len(ELEMENTOS_PADRAO) > 0


def test_gerar_mockup_simples_aceita_elementos_customizados(tmp_path: Path):
    caminho = gerar_mockup_simples(
        tmp_path / "mockup.png", titulo="Tela de login", elementos=["Campo usuário", "Botão Entrar"]
    )

    assert caminho.is_file()


def test_gerar_mockup_simples_cria_diretorios_intermediarios(tmp_path: Path):
    destino = tmp_path / "subpasta" / "mockup.png"

    caminho = gerar_mockup_simples(destino)

    assert caminho.is_file()


def test_gerar_mockup_simples_salva_json_com_geometria_dos_elementos(tmp_path: Path):
    caminho_imagem = gerar_mockup_simples(
        tmp_path / "mockup.png",
        titulo="Tela de login",
        elementos=["Campo usuário", "Botão Entrar"],
        largura=400,
        altura=300,
    )

    caminho_json = caminho_layout_json(caminho_imagem)
    assert caminho_json.is_file()

    layout = json.loads(caminho_json.read_text())
    assert layout["titulo"] == "Tela de login"
    assert layout["largura"] == 400
    assert layout["altura"] == 300
    assert [e["rotulo"] for e in layout["elementos"]] == ["Campo usuário", "Botão Entrar"]
    for elemento in layout["elementos"]:
        assert {"x", "y", "largura", "altura"} <= elemento.keys()
        assert elemento["largura"] > 0 and elemento["altura"] > 0


def test_caminho_layout_json_usa_mesmo_nome_base_com_extensao_json(tmp_path: Path):
    assert caminho_layout_json(tmp_path / "mockup.png") == tmp_path / "mockup.json"
