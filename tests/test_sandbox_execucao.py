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


def test_falha_do_bwrap_ao_montar_sandbox_nao_vira_resultado_de_comando(tmp_path: Path, projeto: Path):
    """Reproduz sem depender do host: um `bwrap` que falha antes de rodar
    o comando (ex.: RTM_NEWADDR bloqueado por AppArmor, como no runner do
    GitHub Actions) precisa levantar erro, não devolver um
    ResultadoExecucao como se o comando dentro do sandbox tivesse rodado
    e saído com código != 0."""
    bwrap_falso = tmp_path / "bwrap_falso.sh"
    bwrap_falso.write_text(
        "#!/bin/sh\necho 'bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted' >&2\nexit 1\n"
    )
    bwrap_falso.chmod(0o755)

    with pytest.raises(SandboxIndisponivelError):
        executar_comando_sandbox(
            projeto, ["/bin/echo", "x"], ConfiguracaoSandbox(comando_bwrap=str(bwrap_falso))
        )


def test_comando_inexistente_dentro_do_sandbox_vira_resultado_nao_erro(projeto: Path):
    # "bwrap: execvp <comando>: ..." é o sandbox funcionando normalmente
    # e recusando rodar um binário que não existe (ex.: pytest não
    # instalado) — não é falha de infraestrutura do bwrap, então não
    # deve levantar SandboxIndisponivelError (visto na prática: o
    # orquestrador tratando isso como "sandbox quebrada" em vez de só
    # "comando não encontrado").
    resultado = executar_comando_sandbox(
        projeto, ["comando_que_nao_existe_de_verdade_xyz"], ConfiguracaoSandbox(timeout_segundos=10)
    )
    assert resultado.codigo_saida != 0
    assert "No such file or directory" in resultado.stderr


def test_executar_pos_inspecao_recusa_sem_liberacao():
    relatorio = {"pode_auto_prosseguir": False, "diretorio_extraido": "/tmp"}
    with pytest.raises(RiscoNaoRevisadoError):
        executar_pos_inspecao(relatorio, [["/bin/echo", "x"]])


def test_executar_pos_inspecao_roda_quando_liberado(projeto: Path):
    relatorio = {"pode_auto_prosseguir": True, "diretorio_extraido": str(projeto)}
    resultados = executar_pos_inspecao(relatorio, [["/bin/ls", "/work"]], ConfiguracaoSandbox(timeout_segundos=10))
    assert len(resultados) == 1
    assert resultados[0].codigo_saida == 0
