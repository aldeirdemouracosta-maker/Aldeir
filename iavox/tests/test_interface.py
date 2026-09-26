"""
Teste da interface do IAVOX dirigida pelo teclado, como um usuário de
leitor de tela faria: F1..F5, Esc, Enter, Espaço e Ctrl+Shift+M.
Roda sem monitor (QT_QPA_PLATFORM=offscreen).
"""
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt5")

from PyQt5.QtCore import Qt  # noqa: E402
from PyQt5.QtTest import QTest  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent.parent))

TEXTO = (
    "O IAVOX é uma suíte de acessibilidade que funciona junto com o DOSVOX. "
    "Ele lê documentos em PDF, descreve imagens e ajuda o aluno a estudar. "
    "Todas as funções rodam no próprio computador, sem depender da internet."
)


@pytest.fixture
def janela(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    # sem Ollama de verdade: o EstudaVox usa o modo simples
    import iavox_pdf_audio.core.summarizer as summ
    monkeypatch.setattr(summ.TextSummarizer, "is_available", lambda self: False)

    app = QApplication.instance() or QApplication([])
    from gui.contexto import Config
    from gui.janela import JanelaIAVOX

    w = JanelaIAVOX(Config(feedback_sonoro=False))
    w.show()
    QApplication.setActiveWindow(w)
    QTest.qWaitForWindowActive(w)
    yield w
    w.close()
    app.processEvents()


def esperar(condicao, ms=5000) -> bool:
    """Equivalente ao QTest.qWaitFor (que o PyQt5 não expõe)."""
    import time
    fim = time.monotonic() + ms / 1000
    while time.monotonic() < fim:
        QApplication.processEvents()
        if condicao():
            return True
        QTest.qWait(20)
    return condicao()


def tecla(w, key, mod=Qt.NoModifier):
    QTest.keyClick(QApplication.focusWidget() or w, key, mod)
    QApplication.processEvents()


def test_f1_a_f5_e_esc_navegam(janela):
    esperado = {Qt.Key_F1: "leitor", Qt.Key_F2: "fala", Qt.Key_F3: "olha",
                Qt.Key_F4: "estuda", Qt.Key_F5: "atividade"}
    for key, nome in esperado.items():
        tecla(janela, key)
        assert janela.pilha.currentWidget() is janela.paginas[nome]
        tecla(janela, Qt.Key_Escape)
        assert janela.pilha.currentWidget() is janela.inicio
    # Tab/Enter no cartão focado também abre o módulo
    assert QApplication.focusWidget() is janela.inicio.cartoes["leitor"]
    tecla(janela, Qt.Key_Return)
    assert janela.pilha.currentWidget() is janela.paginas["leitor"]


def test_estudavox_para_modo_atividade_com_confirmacao(janela, tmp_path):
    tecla(janela, Qt.Key_F4)
    estuda = janela.paginas["estuda"]
    estuda.entrada.setPlainText(TEXTO)
    estuda.b_gerar.click()
    assert esperar(lambda: estuda.estudo is not None, 5000)
    assert "PERGUNTAS" in estuda.saida.toPlainText()
    assert janela.robo_inicio.estado == "confirmando"

    estuda.b_praticar.click()
    ativ = janela.paginas["atividade"]
    assert janela.pilha.currentWidget() is ativ
    assert ativ.contador.text().startswith("PERGUNTA 1 DE")
    total = len(ativ.perguntas)

    # simula a transcrição da voz e confirma com Enter
    ativ.voz._confirmar("O IAVOX lê PDFs para mim.")
    assert ativ.confirmacao.isVisible()
    tecla(janela, Qt.Key_Return)
    assert ativ.respostas[0][1] == "O IAVOX lê PDFs para mim."
    assert janela.ctx.caderno.itens[-1].modulo == "Atividade"
    assert esperar(lambda: ativ.contador.text().startswith("PERGUNTA 2"), 3000)

    # Esc na confirmação cancela a resposta, sem sair da tela
    ativ.voz._confirmar("resposta errada")
    tecla(janela, Qt.Key_Escape)
    assert not ativ.confirmacao.isVisible()
    assert janela.pilha.currentWidget() is ativ
    assert len(ativ.respostas) == 1

    # pular o resto conclui a atividade
    for _ in range(total - 1):
        ativ.b_pular.click()
    assert ativ.contador.text() == "ATIVIDADE CONCLUÍDA"


def test_falavox_espaco_regrava_enter_envia(janela, tmp_path, monkeypatch):
    from gui.paginas import RespostaPorVoz

    chamadas = []
    monkeypatch.setattr(RespostaPorVoz, "iniciar", lambda self: chamadas.append("gravar"))

    # Ctrl+Shift+M na tela inicial abre o FalaVox e começa a gravar
    tecla(janela, Qt.Key_M, Qt.ControlModifier | Qt.ShiftModifier)
    fala = janela.paginas["fala"]
    assert janela.pilha.currentWidget() is fala
    assert chamadas == ["gravar"]

    fala.voz._confirmar("Minha resposta falada")
    tecla(janela, Qt.Key_Space)
    assert chamadas == ["gravar", "gravar"]           # Espaço = gravar novamente

    fala.voz._confirmar("Minha resposta falada")
    tecla(janela, Qt.Key_Return)                      # Enter = confirmar
    respostas = (tmp_path / "IAVOX_respostas.txt").read_text(encoding="utf-8")
    assert "Minha resposta falada" in respostas
    assert QApplication.clipboard().text() == "Minha resposta falada"
    assert fala.historico.item(0).text() == "Minha resposta falada"

    # Mini Caderno (botão Atividade da barra) mostra o registro
    janela.botoes_nav["caderno"].click()
    cad = janela.paginas["caderno"]
    assert cad.lista.count() == 1
    assert "FalaVox" in cad.lista.item(0).text()
    assert (tmp_path / ".iavox" / "caderno.json").exists()


def test_leitor_le_pdf_e_mostra_resumo_do_mockup(janela):
    tecla(janela, Qt.Key_F1)
    leitor = janela.paginas["leitor"]
    leitor.descrever.setChecked(False)
    leitor._definir_pdf(str(Path(__file__).parent / "sample.pdf"))
    assert esperar(lambda: "página" in leitor.doc_info.text(), 5000)
    assert "2 páginas" in leitor.doc_info.text() and "texto nativo" in leitor.doc_info.text()
    leitor.motor.setCurrentIndex(leitor.motor.findData("offline"))
    leitor.gerar.click()
    assert esperar(lambda: leitor.play.isEnabled(), 20000)
    etapas = [leitor.etapas.item(i).text() for i in range(leitor.etapas.count())]
    assert etapas[0] == "[ok] Texto extraído (2 páginas (texto nativo))"
    assert etapas[-1].startswith("[ok] Áudio salvo em")
    assert Path(leitor.audio_atual).stat().st_size > 1000
    assert "Acessibilidade" in leitor.saida.toPlainText()
