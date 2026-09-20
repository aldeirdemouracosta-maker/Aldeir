# Sandbox de execução — a etapa SANDBOX do fluxo de ZIP

Completa o fluxo obrigatório descrito em `importador_zip/README.md`:

```
... SNAPSHOT → SANDBOX → BUILD/TEST
                  ↑
         sandbox_execucao/executar_sandbox.py
```

Usa `bubblewrap` (bwrap) — sandboxing sem privilégio de root e sem
daemon, adequado para uma máquina de desenvolvedor único (ver
`ARQUITETURA_FABRICA_LOCAL_IA.md`). Testado neste ambiente: bloqueia
rede por padrão, confina escrita ao diretório do projeto (montado em
`/work`, tudo mais é somente leitura), aplica timeout de parede e
limite de memória (`RLIMIT_AS`), e mata o grupo de processos inteiro
se estourar o tempo.

## Pré-requisito

```bash
sudo apt install bubblewrap
```

Se `bwrap` não estiver instalado, `executar_comando_sandbox` levanta
`SandboxIndisponivelError` — nunca cai para execução direta sem
isolamento. Essa é uma propriedade de segurança deliberada: uma falha
alta e visível é sempre preferível a rodar código não confiável sem
sandbox.

## Uso

Como CLI:

```bash
python3 executar_sandbox.py /caminho/do/projeto -- python3 -m pytest
```

Como biblioteca, encadeado ao portão do `importador_zip`:

```python
from pathlib import Path
from dataclasses import asdict
from importador_zip.inspecionar_zip import analisar_projeto
from sandbox_execucao.executar_sandbox import (
    executar_pos_inspecao, ConfiguracaoSandbox, RiscoNaoRevisadoError,
)

relatorio = asdict(analisar_projeto(Path("projeto.zip"), Path("/tmp/analise")))

try:
    resultados = executar_pos_inspecao(
        relatorio,
        comandos=[["pip", "install", "-r", "requirements.txt"], ["pytest"]],
        config=ConfiguracaoSandbox(timeout_segundos=120, memoria_max_mb=1024),
    )
except RiscoNaoRevisadoError:
    # relatorio["arquivos_de_risco"] / relatorio["padroes_suspeitos"]
    # explicam o motivo — pedir confirmação humana antes de tentar de
    # novo com permitir_apesar_do_risco=True.
    ...
```

`executar_pos_inspecao` recusa rodar (`RiscoNaoRevisadoError`) quando
`relatorio["pode_auto_prosseguir"]` é `False`, a menos que o chamador
passe `permitir_apesar_do_risco=True` depois de um humano revisar os
achados — o portão dos dois módulos só se abre junto.

## O que é isolado, e o que não é

Isolado (testado): namespace de rede (`--unshare-net`, sem acesso à
rede por padrão), namespace de PID/IPC/UTS, escrita restrita a
`/work` (todo o resto montado `--ro-bind`), timeout de parede,
`RLIMIT_AS` (memória) e `RLIMIT_CPU`.

Não isolado por este módulo (limitações conhecidas do bwrap sem
privilégio extra): namespace de usuário completo depende do kernel
permitir `unprivileged_userns_clone` — usamos `--unshare-user-try`,
que degrada graciosamente em vez de falhar se o kernel não permitir;
não há limite de I/O de disco nem de número de processos (`nproc`) —
se isso importar para o seu caso de uso, combine com `cgroups`
(`systemd-run --scope -p MemoryMax=... -p TasksMax=...`) por fora
deste script.

**Toolchain fora de `/usr`, `/bin`, `/sbin`, `/lib`, `/lib64`, `/etc`,
`/opt` não fica visível dentro do sandbox.** `/opt` foi incluído
justamente porque é onde vivem instalações comuns de toolchain (ex.:
o Python do `actions/setup-python` no GitHub Actions fica em
`/opt/hostedtoolcache` — sem esse bind, `python3 -m pytest` dentro do
sandbox não encontrava o `pytest` instalado pelo `pip` no runner,
mesmo com tudo certo do lado de fora). Instalações em diretório de
usuário (`~/.pyenv`, `~/.nvm`, `~/.rbenv` etc.) continuam fora do
alcance do sandbox — a alternativa é um ambiente virtual/`node_modules`
dentro do próprio diretório do projeto, que fica visível via `/work`.

## Habilitar rede (quando necessário)

Alguns builds precisam baixar dependências. Isso é uma escolha
explícita por comando, nunca o padrão:

```python
ConfiguracaoSandbox(permitir_rede=True)
```

Prefira rodar a instalação de dependências (com rede) e o
build/test (sem rede) como comandos separados em `executar_pos_inspecao`,
cada um com sua própria `ConfiguracaoSandbox`.
