import shutil
from pathlib import Path

import pytest

from dataclasses import asdict

from analisador_projeto.analisar_completude import (
    analisar_completude,
    detectar_linguagem_principal,
    encontrar_funcoes_incompletas_python,
    encontrar_modulos_stub,
    encontrar_todos,
    formatar_diagnostico_para_prompt,
)


@pytest.fixture
def projeto_incompleto(tmp_path: Path) -> Path:
    (tmp_path / "app.py").write_text(
        "def soma(a, b):\n"
        "    return a + b\n"
        "\n"
        "def subtrai(a, b):\n"
        "    # TODO: implementar de verdade\n"
        "    pass\n"
        "\n"
        "def multiplica(a, b):\n"
        "    raise NotImplementedError\n"
        "\n"
        "def divide(a, b):\n"
        '    """Docstring apenas, sem corpo real ainda"""\n'
    )
    (tmp_path / "utils.py").write_text("import os\n")
    testes = tmp_path / "tests"
    testes.mkdir()
    (testes / "test_app.py").write_text(
        "from app import soma, subtrai\n\n"
        "def test_soma():\n"
        "    assert soma(2, 3) == 5\n\n"
        "def test_subtrai():\n"
        "    assert subtrai(5, 2) == 3\n"
    )
    return tmp_path


@pytest.fixture
def projeto_completo(tmp_path: Path) -> Path:
    (tmp_path / "app.py").write_text("def soma(a, b):\n    return a + b\n")
    testes = tmp_path / "tests"
    testes.mkdir()
    (testes / "test_app.py").write_text(
        "from app import soma\n\ndef test_soma():\n    assert soma(2, 3) == 5\n"
    )
    return tmp_path


def test_detectar_linguagem_principal_python(projeto_incompleto: Path):
    assert detectar_linguagem_principal(projeto_incompleto) == "Python"


def test_encontrar_todos(projeto_incompleto: Path):
    achados = encontrar_todos(projeto_incompleto)
    assert len(achados) == 1
    assert "TODO" in achados[0].detalhe


def test_encontrar_todos_ignora_palavra_todo_em_portugues(tmp_path: Path):
    # "todo" (português para "every/all") não pode ser confundido com o
    # marcador de código TODO — visto na prática num comentário real do
    # projeto ("nem todo motor obedece...").
    (tmp_path / "app.py").write_text(
        "# nem todo motor obedece a mesma prioridade\n"
        "def selecionar():\n"
        "    return True\n"
    )

    achados = encontrar_todos(tmp_path)

    assert achados == []


def test_encontrar_funcoes_incompletas_detecta_pass_raise_e_so_docstring(projeto_incompleto: Path):
    achados = encontrar_funcoes_incompletas_python(projeto_incompleto)
    nomes = {a.detalhe for a in achados}
    assert len(achados) == 3
    assert any("subtrai" in n for n in nomes)
    assert any("multiplica" in n for n in nomes)
    assert any("divide" in n for n in nomes)


def test_encontrar_funcoes_incompletas_nao_marca_funcao_implementada(projeto_incompleto: Path):
    achados = encontrar_funcoes_incompletas_python(projeto_incompleto)
    assert not any("soma" in a.detalhe for a in achados)


def test_encontrar_modulos_stub(projeto_incompleto: Path):
    achados = encontrar_modulos_stub(projeto_incompleto)
    assert len(achados) == 1
    assert achados[0].arquivo == "utils.py"


def test_formatar_diagnostico_para_prompt_inclui_achados_principais(projeto_incompleto: Path):
    relatorio = asdict(analisar_completude(projeto_incompleto, rodar_testes_automaticos=False))
    texto = formatar_diagnostico_para_prompt(relatorio)

    assert "Python" in texto
    assert "3 função/funções incompleta(s)" in texto
    assert "subtrai" in texto
    assert "TODO" in texto
    assert f"Estado estimado: {relatorio['estado_estimado_percentual']}%" in texto


def test_relatorio_seguranca_bloqueia_execucao_de_testes(projeto_completo: Path):
    relatorio = analisar_completude(
        projeto_completo, relatorio_seguranca={"pode_auto_prosseguir": False}
    )
    assert relatorio.testes is None
    assert any("não liberou execução automática" in obs for obs in relatorio.observacoes)


@pytest.mark.skipif(shutil.which("bwrap") is None, reason="bubblewrap não instalado")
class TestComSandboxReal:
    def test_projeto_completo_estado_100(self, projeto_completo: Path):
        relatorio = analisar_completude(projeto_completo)
        assert relatorio.funcoes_incompletas == []
        assert relatorio.testes["passaram"] == 1
        assert relatorio.testes["falharam"] == 0
        assert relatorio.estado_estimado_percentual == 100

    def test_projeto_incompleto_estado_baixo_e_conta_teste_falho(self, projeto_incompleto: Path):
        relatorio = analisar_completude(projeto_incompleto)
        assert relatorio.testes["passaram"] == 1
        assert relatorio.testes["falharam"] == 1
        assert relatorio.estado_estimado_percentual < 50
