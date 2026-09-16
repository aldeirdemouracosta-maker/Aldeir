import shutil
from pathlib import Path

import pytest

from sandbox_execucao.executar_sandbox import (
    ConfiguracaoSandbox,
    SandboxIndisponivelError,
    executar_comando_sandbox,
    executar_pos_inspecao,
    RiscoNaoRevisadoError,
)

pytestmark = pytest.mark.skipif(
    shutil.which("bwrap") is None,
    reason="bubblewrap (bwrap) não instalado neste ambiente — sudo apt install bubblewrap",
)


@pytest.fixture
def projeto(tmp_path: Path) -> Path:
    (tmp_path / "arquivo.txt").write_text("conteudo\n")
    return tmp_path


def test_comando_simples_roda_e_retorna_codigo_zero(projeto: Path):
    resultado = executar_comando_sandbox(projeto, ["/bin/ls", "/work"], ConfiguracaoSandbox(timeout_segundos=10))
    assert resultado.codigo_saida == 0
    assert "arquivo.txt" in resultado.stdout
    assert resultado.expirou is False


def test_escrita_dentro_do_projeto_persiste_no_host(projeto: Path):
    executar_comando_sandbox(
        projeto, ["/bin/sh", "-c", "echo novo > /work/gerado.txt"], ConfiguracaoSandbox(timeout_segundos=10)
    )
    assert (projeto / "gerado.txt").read_text().strip() == "novo"


def test_rede_bloqueada_por_padrao(projeto: Path):
    resultado = executar_comando_sandbox(
        projeto,
        ["/bin/sh", "-c", "curl -s --max-time 3 https://example.com >/dev/null && echo OK || echo BLOQUEADO"],
        ConfiguracaoSandbox(timeout_segundos=10),
    )
    assert resultado.stdout.strip() == "BLOQUEADO"


def test_escrita_fora_do_work_bloqueada(projeto: Path):
    resultado = executar_comando_sandbox(
        projeto,
        ["/bin/sh", "-c", "touch /usr/arquivo_de_teste_proibido 2>&1 && echo ESCREVEU || echo BLOQUEADO"],
        ConfiguracaoSandbox(timeout_segundos=10),
    )
    assert "BLOQUEADO" in resultado.stdout
    assert "ESCREVEU" not in resultado.stdout


def test_timeout_mata_processo_travado(projeto: Path):
    resultado = executar_comando_sandbox(projeto, ["/bin/sleep", "10"], ConfiguracaoSandbox(timeout_segundos=1))
    assert resultado.expirou is True
    assert resultado.tempo_segundos < 5


def test_bwrap_ausente_levanta_erro_alto(projeto: Path):
    with pytest.raises(SandboxIndisponivelError):
        executar_comando_sandbox(
            projeto, ["/bin/echo", "x"], ConfiguracaoSandbox(comando_bwrap="bwrap_inexistente_xyz")
        )


def test_executar_pos_inspecao_recusa_sem_liberacao():
    relatorio = {"pode_auto_prosseguir": False, "diretorio_extraido": "/tmp"}
    with pytest.raises(RiscoNaoRevisadoError):
        executar_pos_inspecao(relatorio, [["/bin/echo", "x"]])


def test_executar_pos_inspecao_roda_quando_liberado(projeto: Path):
    relatorio = {"pode_auto_prosseguir": True, "diretorio_extraido": str(projeto)}
    resultados = executar_pos_inspecao(relatorio, [["/bin/ls", "/work"]], ConfiguracaoSandbox(timeout_segundos=10))
    assert len(resultados) == 1
    assert resultados[0].codigo_saida == 0
