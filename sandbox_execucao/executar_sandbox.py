#!/usr/bin/env python3
"""Executor de build/test isolado — a etapa SANDBOX do fluxo de
importação de ZIP (ver importador_zip/README.md).

Usa `bubblewrap` (bwrap) para isolar o processo em namespaces
separados (rede, PID, IPC, UTS) e limitar escrita ao diretório do
projeto, mais limites de CPU/memória via `resource.setrlimit`. Nunca
executa um comando fora do sandbox: se `bwrap` não estiver disponível,
levanta `SandboxIndisponivelError` em vez de cair para execução direta
— uma falha alta e visível é sempre preferível a rodar código não
confiável sem isolamento.

Pré-requisito no Ubuntu: `sudo apt install bubblewrap`.

Uso:
    python3 executar_sandbox.py <diretorio_projeto> -- <comando...>
"""

import argparse
import os
import resource
import shutil
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

CAMINHOS_SOMENTE_LEITURA = ["/usr", "/bin", "/sbin", "/lib", "/lib64", "/etc"]


class SandboxIndisponivelError(Exception):
    """`bwrap` não encontrado no sistema. Nunca execute sem sandbox
    como alternativa — instale o bubblewrap (`apt install bubblewrap`)."""


class RiscoNaoRevisadoError(Exception):
    """O relatório do importador_zip não liberou execução automática
    e nenhuma revisão humana explícita foi concedida."""


@dataclass
class ConfiguracaoSandbox:
    timeout_segundos: int = 300
    memoria_max_mb: int = 2048
    permitir_rede: bool = False
    comando_bwrap: str = "bwrap"


@dataclass
class ResultadoExecucao:
    comando: list
    codigo_saida: Optional[int]
    stdout: str
    stderr: str
    expirou: bool
    tempo_segundos: float


def bwrap_disponivel(comando_bwrap: str = "bwrap") -> bool:
    return shutil.which(comando_bwrap) is not None


def montar_argumentos_bwrap(diretorio_projeto: Path, permitir_rede: bool) -> list:
    args = []
    for caminho in CAMINHOS_SOMENTE_LEITURA:
        if Path(caminho).exists():
            args += ["--ro-bind", caminho, caminho]

    args += ["--bind", str(diretorio_projeto.resolve()), "/work"]
    args += ["--tmpfs", "/tmp"]
    args += ["--proc", "/proc"]
    args += ["--dev", "/dev"]
    args += ["--chdir", "/work"]
    args += ["--die-with-parent"]
    args += ["--unshare-ipc", "--unshare-pid", "--unshare-uts"]
    args += ["--unshare-user-try", "--unshare-cgroup-try"]
    if not permitir_rede:
        args += ["--unshare-net"]

    return args


def _aplicar_limites(config: ConfiguracaoSandbox):
    def limitar():
        os.setsid()
        limite_cpu = config.timeout_segundos + 5  # folga sobre o timeout de parede
        resource.setrlimit(resource.RLIMIT_CPU, (limite_cpu, limite_cpu))
        limite_memoria = config.memoria_max_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (limite_memoria, limite_memoria))

    return limitar


def executar_comando_sandbox(
    diretorio_projeto: Path, comando: list, config: ConfiguracaoSandbox = None
) -> ResultadoExecucao:
    """Roda `comando` isolado dentro de `diretorio_projeto` (montado em /work)."""
    config = config or ConfiguracaoSandbox()

    if not bwrap_disponivel(config.comando_bwrap):
        raise SandboxIndisponivelError(
            f"'{config.comando_bwrap}' não encontrado. "
            "Instale com: sudo apt install bubblewrap"
        )

    args_bwrap = montar_argumentos_bwrap(diretorio_projeto, config.permitir_rede)
    comando_completo = [config.comando_bwrap] + args_bwrap + ["--"] + comando

    inicio = time.monotonic()
    processo = subprocess.Popen(
        comando_completo,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        preexec_fn=_aplicar_limites(config),
    )

    try:
        stdout, stderr = processo.communicate(timeout=config.timeout_segundos)
        expirou = False
        codigo_saida = processo.returncode
    except subprocess.TimeoutExpired:
        os.killpg(processo.pid, signal.SIGKILL)
        stdout, stderr = processo.communicate()
        expirou = True
        codigo_saida = None

    if not expirou and codigo_saida != 0 and stderr.startswith("bwrap: "):
        # O próprio bwrap falhou ao montar o sandbox (ex.: namespace de
        # rede bloqueado por política do host) — isso nunca chegou a
        # rodar `comando`. Tratar como resultado de execução (código de
        # saída do comando) esconderia uma falha de infraestrutura como
        # se fosse o comportamento do projeto sendo testado.
        raise SandboxIndisponivelError(f"bwrap falhou ao montar o sandbox: {stderr.strip()}")

    return ResultadoExecucao(
        comando=comando,
        codigo_saida=codigo_saida,
        stdout=stdout,
        stderr=stderr,
        expirou=expirou,
        tempo_segundos=time.monotonic() - inicio,
    )


def executar_pos_inspecao(
    relatorio: dict,
    comandos: list,
    config: ConfiguracaoSandbox = None,
    permitir_apesar_do_risco: bool = False,
) -> list:
    """Encadeia comandos (ex.: build, depois test) usando o relatório do
    importador_zip como portão. Para no primeiro comando que falhar.
    """
    if not relatorio.get("pode_auto_prosseguir") and not permitir_apesar_do_risco:
        raise RiscoNaoRevisadoError(
            "importador_zip sinalizou risco e não houve revisão humana "
            "explícita (permitir_apesar_do_risco=True)."
        )

    diretorio_projeto = Path(relatorio["diretorio_extraido"])
    resultados = []
    for comando in comandos:
        resultado = executar_comando_sandbox(diretorio_projeto, comando, config)
        resultados.append(resultado)
        if resultado.expirou or resultado.codigo_saida != 0:
            break

    return resultados


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("diretorio_projeto", type=Path)
    parser.add_argument("comando", nargs=argparse.REMAINDER)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--memoria-mb", type=int, default=2048)
    parser.add_argument("--permitir-rede", action="store_true")
    args = parser.parse_args()

    comando = args.comando
    if comando and comando[0] == "--":
        comando = comando[1:]
    if not comando:
        parser.error("informe o comando a executar após '--'")

    config = ConfiguracaoSandbox(
        timeout_segundos=args.timeout,
        memoria_max_mb=args.memoria_mb,
        permitir_rede=args.permitir_rede,
    )
    resultado = executar_comando_sandbox(args.diretorio_projeto, comando, config)

    print(f"código de saída: {resultado.codigo_saida} (expirou={resultado.expirou})")
    print(f"tempo: {resultado.tempo_segundos:.2f}s")
    print("--- stdout ---")
    print(resultado.stdout)
    print("--- stderr ---")
    print(resultado.stderr)


if __name__ == "__main__":
    main()
