"""Testes dos módulos da suíte IAVOX (F1 a F5 e Mini Caderno) — sem interface gráfica."""
import sys
import threading
from datetime import datetime
from http.server import HTTPServer
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).parent.parent))

from iavox_pdf_audio.suite import ambiente, voz_entrada
from iavox_pdf_audio.suite.caderno import MAX_ITENS_NA_TELA, MiniCaderno
from iavox_pdf_audio.suite.estudo import EstudaVox, ler_texto_de_arquivo, perguntas_simples
from iavox_pdf_audio.suite.olhavox import descrever_imagem, ler_texto_imagem
from iavox_pdf_audio.core.image_description import ImageDescriber
from tests.fake_ollama import FakeOllamaHandler

SAMPLE_PDF = Path(__file__).parent / "sample.pdf"
TEXTO = (
    "O IAVOX é uma suíte de acessibilidade que funciona junto com o DOSVOX. "
    "Ele lê documentos em PDF, descreve imagens e ajuda o aluno a estudar. "
    "Todas as funções rodam no próprio computador, sem depender da internet. "
    "O professor orientador acompanha as atividades pelo Mini Caderno. "
    "As respostas podem ser dadas com a voz e confirmadas pelo teclado."
)


@pytest.fixture
def ollama_fake():
    servidor = HTTPServer(("localhost", 0), FakeOllamaHandler)
    t = threading.Thread(target=servidor.serve_forever, daemon=True)
    t.start()
    yield f"http://localhost:{servidor.server_port}"
    servidor.shutdown()


SEM_OLLAMA = "http://localhost:9"  # porta fechada: simula Ollama desligado


# ------------------------------------------------------------ Mini Caderno

def test_caderno_registra_persiste_e_limita_a_tela(tmp_path):
    arq = tmp_path / "caderno.json"
    cad = MiniCaderno(arq)
    for i in range(35):
        cad.registrar("LeitorVox", f"item {i}", quando=datetime(2025, 5, 24, 14, i % 60))
    assert len(MiniCaderno(arq).itens) == 35          # persistiu em disco
    tela = cad.itens_na_tela()
    assert len(tela) == MAX_ITENS_NA_TELA == 30
    assert tela[0].texto == "item 34"                  # mais recente primeiro
    assert tela[0].data_hora == "24/05/2025 14:34"


def test_caderno_txt_fala_e_limpar(tmp_path):
    cad = MiniCaderno(tmp_path / "c.json")
    assert "vazio" in cad.como_fala()
    cad.registrar("FalaVox", "Resposta sobre células-tronco")
    cad.registrar("OlhaVox", "Gráfico de barras colorido")
    txt = cad.salvar_txt(tmp_path / "caderno.txt")
    conteudo = txt.read_text(encoding="utf-8")
    assert "MINI CADERNO IAVOX" in conteudo and "células-tronco" in conteudo
    assert cad.como_fala().startswith("Mini Caderno com 2 itens. OlhaVox")
    cad.limpar()
    assert MiniCaderno(tmp_path / "c.json").itens == []


def test_caderno_texto_longo_e_arquivo_corrompido(tmp_path):
    arq = tmp_path / "c.json"
    arq.write_text("{isto não é json", encoding="utf-8")
    cad = MiniCaderno(arq)                      # não pode quebrar
    assert cad.itens == []
    item = cad.registrar("EstudaVox", "x" * 10000)
    assert len(item.texto) < 4100 and item.texto.endswith("[...]")
    assert len(item.resumo) <= 90


# ------------------------------------------------------------ EstudaVox

def test_estudavox_com_ia(ollama_fake):
    estudo = EstudaVox(ollama_url=ollama_fake).estudar(TEXTO, "curto", n_perguntas=3)
    assert estudo.usou_ia
    assert "Resumo curto simulado" in estudo.resumo
    assert estudo.perguntas == [
        "O que é o IAVOX?",
        "Como o IAVOX ajuda quem usa o DOSVOX?",
        "Por que funcionar offline é importante?",
    ]
    assert "Pergunta 2. Como o IAVOX" in estudo.como_fala()


def test_estudavox_sem_ia_ainda_responde():
    estudo = EstudaVox(ollama_url=SEM_OLLAMA).estudar(TEXTO, n_perguntas=3)
    assert not estudo.usou_ia
    assert estudo.resumo.startswith("O IAVOX é uma suíte")
    assert len(estudo.perguntas) == 3
    assert all(p.endswith("?") for p in estudo.perguntas)


def test_estudavox_texto_vazio():
    with pytest.raises(ValueError):
        EstudaVox(ollama_url=SEM_OLLAMA).estudar("   ")
    assert perguntas_simples("curto.") == []


def test_ler_texto_de_pdf_e_txt(tmp_path):
    assert "Acessibilidade" in ler_texto_de_arquivo(SAMPLE_PDF)
    ansi = tmp_path / "ansi.txt"
    ansi.write_bytes("Atenção: questão".encode("cp1252"))  # arquivo salvo pelo EDIVOX
    assert ler_texto_de_arquivo(ansi) == "Atenção: questão"


# ------------------------------------------------------------ OlhaVox / OCR

def _imagem_com_texto(caminho: Path) -> Path:
    img = Image.new("RGB", (900, 220), "white")
    d = ImageDraw.Draw(img)
    try:
        fonte = ImageFont.truetype("DejaVuSans.ttf", 64)
    except OSError:
        fonte = ImageFont.load_default()
    d.text((30, 70), "LEITURA ACESSIVEL", fill="black", font=fonte)
    img.save(caminho)
    return caminho


tesseract = pytest.mark.skipif(not ambiente.checar_ocr().ok, reason="Tesseract não instalado")


@tesseract
def test_ocr_de_imagem(tmp_path):
    texto = ler_texto_imagem(_imagem_com_texto(tmp_path / "t.png"))
    assert "LEITURA" in texto.upper()


@tesseract
def test_olhavox_com_ia_junta_descricao_e_texto(tmp_path, ollama_fake):
    d = descrever_imagem(_imagem_com_texto(tmp_path / "t.png"), ImageDescriber(ollama_url=ollama_fake))
    assert d.usou_ia and "Gráfico de barras" in d.descricao
    assert "Texto na imagem:" in d.como_fala() and "LEITURA" in d.como_fala().upper()


def test_olhavox_sem_ia_descreve_formato(tmp_path):
    caminho = tmp_path / "foto.png"
    Image.new("RGB", (400, 200), "blue").save(caminho)
    d = descrever_imagem(caminho, ImageDescriber(ollama_url=SEM_OLLAMA))
    assert not d.usou_ia
    assert "horizontal" in d.descricao and "400 por 200" in d.descricao


# ------------------------------------------------------------ FalaVox / ambiente

def test_inserir_resposta_acrescenta_ao_arquivo(tmp_path):
    arq = tmp_path / "respostas.txt"
    voz_entrada.inserir_resposta("primeira", arq)
    voz_entrada.inserir_resposta("segunda", arq)
    linhas = arq.read_text(encoding="utf-8").splitlines()
    assert len(linhas) == 2 and linhas[1].endswith("] segunda")


def test_status_do_ambiente(ollama_fake):
    ok = ambiente.checar_modelos_locais(ollama_fake)
    assert ok.ok and "llava:7b" in ok.detalhe
    desligado = ambiente.checar_modelos_locais(SEM_OLLAMA)
    assert not desligado.ok and "não está rodando" in desligado.fala
    nomes = [s.nome for s in ambiente.checar_tudo()]
    assert nomes == ["DOSVOX", "Microfone", "OCR", "Modelos locais"]
