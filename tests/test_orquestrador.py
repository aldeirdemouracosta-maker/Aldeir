import json
import shutil
from pathlib import Path

import pytest

import orquestrador.orquestrador as orq

pytestmark = pytest.mark.skipif(
    shutil.which("bwrap") is None,
    reason="bubblewrap (bwrap) não instalado neste ambiente — sudo apt install bubblewrap",
)


def _msg_tool_call(id_, nome, argumentos):
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {"id": id_, "type": "function", "function": {"name": nome, "arguments": json.dumps(argumentos)}}
        ],
    }


@pytest.fixture
def projeto(tmp_path: Path) -> Path:
    (tmp_path / "existente.txt").write_text("ola\n")
    return tmp_path


@pytest.fixture(autouse=True)
def _restaurar_selecionar_motor():
    original = orq.selecionar_motor
    yield
    orq.selecionar_motor = original


def test_motor_indisponivel_falha_alto_sem_travar(projeto: Path):
    orq.selecionar_motor = lambda: {"escolhido": None, "base_url": None, "mensagem": "nenhum motor"}
    with pytest.raises(orq.MotorIndisponivelError):
        orq.Orquestrador(projeto).rodar("qualquer instrução")


def test_loop_completo_escreve_arquivo_e_finaliza(projeto: Path, servidor_llm_mock):
    base_url = servidor_llm_mock(
        [
            _msg_tool_call("1", "escrever_arquivo", {"caminho": "saida.txt", "conteudo": "gerado\n"}),
            _msg_tool_call("2", "finalizar", {"resumo": "feito", "sucesso": True}),
        ]
    )
    orq.selecionar_motor = lambda: {"escolhido": "mock", "base_url": base_url}

    resultado = orq.Orquestrador(projeto).rodar("crie saida.txt")

    assert resultado == {"resumo": "feito", "sucesso": True}
    assert (projeto / "saida.txt").read_text() == "gerado\n"


def test_loop_executa_comando_via_sandbox(projeto: Path, servidor_llm_mock):
    base_url = servidor_llm_mock(
        [
            _msg_tool_call("1", "executar_comando", {"comando": ["/bin/cat", "existente.txt"]}),
            _msg_tool_call("2", "finalizar", {"resumo": "verificado", "sucesso": True}),
        ]
    )
    orq.selecionar_motor = lambda: {"escolhido": "mock", "base_url": base_url}

    resultado = orq.Orquestrador(projeto).rodar("leia o arquivo existente")
    assert resultado["sucesso"] is True


def test_escrita_fora_da_raiz_do_projeto_e_bloqueada(projeto: Path, servidor_llm_mock):
    base_url = servidor_llm_mock(
        [
            _msg_tool_call("1", "escrever_arquivo", {"caminho": "../../etc/passwd_teste", "conteudo": "x"}),
            _msg_tool_call("2", "finalizar", {"resumo": "tentei escapar", "sucesso": False}),
        ]
    )
    orq.selecionar_motor = lambda: {"escolhido": "mock", "base_url": base_url}

    orq.Orquestrador(projeto).rodar("tente escrever fora do projeto")
    assert not Path("/etc/passwd_teste").exists()


def test_limite_de_iteracoes_e_respeitado(projeto: Path, servidor_llm_mock):
    base_url = servidor_llm_mock(
        [_msg_tool_call("1", "ler_arquivo", {"caminho": "existente.txt"})]  # nunca chama finalizar
    )
    orq.selecionar_motor = lambda: {"escolhido": "mock", "base_url": base_url}

    with pytest.raises(orq.LimiteDeIteracoesError):
        orq.Orquestrador(projeto, max_iteracoes=3).rodar("nunca termine")
