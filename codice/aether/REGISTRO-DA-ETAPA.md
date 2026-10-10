# REGISTRO DA ETAPA — Aether MVP — 2026-10-10

Snapshot do projeto. Código, testes, scripts, cinco skills locais, README,
pyproject.toml e aether.yaml sem credenciais incluídos. Não existem requirements
ou lockfiles adicionais na raiz. AGENTS.md não foi encontrado. Nenhum código
original foi modificado. Os checks abaixo são HISTÓRICOS confirmados em logs;
pytest, mypy, Ruff, verify e Ollama não foram executados neste empacotamento.

## Funcionalidades implementadas

Agente local AetherAgent e CLI; planejamento e ferramentas de arquivo; skills
locais; embeddings Ollama, indexação/busca LanceDB e cache persistente; GUI nativa
NiceGUI/pywebview com sidebar, chat, scroll, textarea, cards de tools e tema dark;
agente assíncrono, diagnóstico de encerramentos e recuperação dos controles;
contagem determinística com escopo, exclusões e resultados parciais.
Terminal do agente permanece desabilitado, proteções de caminhos preservadas.
Nenhuma instalação de dependência/modelo ou alteração de pesos nesta operação.

## Instalação e execução na cópia extraída

Python 3.12+ e Ollama local são necessários. Modelos devem estar previamente
instalados: confira `ollama list` para qwen3:8b e nomic-embed-text. Não baixar
modelos automaticamente. aether.yaml é a configuração existente e exemplo seguro.

```powershell
cd <pasta-extraida>\Aether-MVP-2026-10-10
py -3.13 -m venv .venv
.venv\Scripts\python.exe -m pip install ".[gui,dev]"
.venv\Scripts\python.exe -m aether.gui.app --path .
# Prévia visual sem execução do agente:
.venv\Scripts\python.exe -m aether.gui.app --path . --demo
.venv\Scripts\aether.exe status .
.venv\Scripts\aether.exe index .
.venv\Scripts\aether.exe search "como funciona o cache" --limit 5
# Checks opcionais (não executados no empacotamento):
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m mypy aether
.venv\Scripts\python.exe -m ruff check aether tests scripts
.venv\Scripts\python.exe scripts/verify.py
```

Instalar dependências exige acesso ao repositório de pacotes. O ZIP não inclui
.venv, modelos, índice vetorial, caches ou chaves. A indexação padrão tinha falha
por caminhos inacessíveis; exclusões explícitas na integração anterior não provam
PASS do comando padrão. Conferir `.aether/evidence/ollama-validation-final.json`
e `.md` para embeddings/LanceDB/cache reais e limitações anteriores.

## Manifesto, cópia e verificação

MANIFESTO.json lista arquivos, tamanhos, SHA-256, exclusões, sanitizações e caminhos
inacessíveis. Sua própria entrada não tem hash/tamanho para evitar autorreferência;
CRC e SHA-256 externo cobrem o manifesto. Strings de credenciais em
`tests/test_evidence.py` são fixtures sintéticas explícitas, preservadas como código.
Evidências copiadas foram sanitizadas por padrões de credenciais, tokens,
autenticação em URLs, e-mails e nomes em diretórios pessoais. Nenhuma credencial
real foi identificada no código/configuração incluídos. A revisão por padrões não
é uma garantia universal contra segredos desconhecidos.

A gravação em C:\Projetos\Aether-registros foi negada pelas permissões desta
sessão. O pacote foi produzido fora do projeto em pasta temporária permitida;
a cópia para o destino solicitado permanece pendente, sem sobrescrever registros.
Os 20 diretórios inacessíveis tests/tmp* não puderam ser incluídos e não se presume
que estejam vazios. Diretórios tmp legítimos acessíveis são preservados, sem filtro
genérico por nome/prefixo. Relatórios históricos refletem suas etapas originais.

## Diagnóstico e resultados da última validação (relatório existente)

Os caminhos das evidências citados abaixo são relativos a `.aether/evidence/`.

# Diagnóstico da contagem e encerramento da GUI

Data: 10/10/2026. Workspace: `C:\Projetos\Aether-antigo`.

## Leitura e limites da investigação

AGENTS.md não foi encontrado no workspace. Foram consultados README, agente,
ferramentas, sessão assíncrona, componentes da GUI e evidências recentes antes de
editar. O plano foi apresentado: reproduzir, instrumentar encerramentos, contar
caminhos deterministicamente e executar os checks. Alterações existentes foram
preservadas. Nenhum modelo, peso ou dependência foi instalado nesta tarefa.

## Causa observada e o que não foi demonstrado

A evidência histórica `1273727164dc4ec38ddb7b5fe915f69e.json` contém apenas a
verificação BLOCKED por ausência de comando executado, sem estado final,
resposta do modelo ou motivo de interrupção. Não permite atribuir a interrupção
relatada a exceção, timeout, limite de passos, truncamento ou chamada inválida.
O código da GUI classificava o resultado por texto, e o agente não persistia um
estado estruturado que permitisse reconstruir o motivo. Esse defeito de
diagnóstico foi identificado e corrigido; a causa da sessão histórica permanece
indeterminada.

A reprodução real do pedido exato, antes da alteração, **concluiu** com
`qwen3:8b`, em 187,485 s, duas iterações e três respostas `done_reason=stop`.
Não houve interrupção por timeout, limite, truncamento ou chamada inválida nessa
reprodução. O modelo usou uma árvore textual e afirmou 32 arquivos, sem contagem
determinística ou aviso sobre acessibilidade. Evidências:
`count-baseline-ollama.json`, `count-baseline-ollama-responses.json` e
`count-baseline-ollama.log`. Essa resposta não comprova o total do projeto.

Com modelo falso, foram reproduzidos encerramentos controlados: excesso de
resposta (0 caracteres de conteúdo + 12.001 de thinking, limite 12.000), timeout,
metadado de truncamento, argumentos inválidos e saída de ferramenta truncada.
`count-fake-limit-reproduction.json` seleciona deliberadamente a rota genérica
antiga para reproduzir o excesso de resposta; não constitui prova da causa
histórica nem integração real. Testes também cobrem conclusão, limites,
aprovação do plano, falhas de contagem, cancelamento e falha do worker/renderizador.

## Correções

- `TaskOutcome` separa conclusão, execução incompleta e falha, com código e
  descrição. O agente registra motivos específicos e tamanhos medidos quando
  há limite de resposta; Ollama expõe metadados de encerramento sem inseri-los
  no contexto de conversa.
- A GUI exibe o motivo no cabeçalho e chat. O bloco `finally` restaura cada
  controle individualmente: input, envio, skills e reinício. Cancelamento fecha
  a sessão; uma inferência em thread pode ainda encerrar, e seu agente não é
  reutilizado enquanto isso. Desconexão não tenta atualizar widgets descartados.
- As evidências persistem `task_outcome` e resultados estruturados das ferramentas,
  separadamente dos comandos de verificação. BLOCKED em verificação não prova
  interrupção de uma tarefa de leitura.
- `count_python_files` percorre caminhos de arquivos regulares, sem ler conteúdo
  e sem contar uma árvore textual. O pedido exato do usuário tem uma rota
  determinística, sem chamada ao modelo, com aprovação de plano e limites existentes
  respeitados. Pedidos mais gerais podem chamar a ferramenta pelo modelo.

## Escopo e contagem real

Escopo `.` recursivo, extensão `.py` sem distinguir maiúsculas, contagem de
caminhos regulares. Diretórios excluídos: `.git`, `.venv`, `venv`, `__pycache__`,
`.pytest_cache`, `.mypy_cache`, `.ruff_cache`, `.cache`. Locais gerados conhecidos
excluídos na raiz: `.buildtmp`, `.tmp`, `.aether/evidence`, `.aether/lancedb`,
`.aether/gui-install-tmp`. Links/junctions não são seguidos. Diretórios `tmp`
legítimos são incluídos; não existe exclusão genérica por prefixo `tmp`.
Confinamento de caminhos continua ativo. Terminal do agente continua desabilitado.

O pedido exato após a correção encontrou **46 arquivos acessíveis**, com
**20 caminhos inacessíveis** em `tests/tmp*`, todos com `PermissionError:
[WinError 5] Acesso negado`. O estado é `incomplete / partial_count`; o total
completo não foi confirmado. A lista integral consta em
`count-fixed-filesystem.json` e `466c8465b07c462290b80477c2038ba6.json`.
Essa execução usou o sistema de arquivos real e um cliente que proíbe inferência;
não deve ser chamada de integração com Ollama.

Uma integração adicional **real** com `qwen3:8b`, em variante que explicitamente
pede a ferramenta, concluiu em **157,382 s**: plano, chamada válida a
`count_python_files(path=".")` e resposta final informando 46 e os 20 inacessíveis.
As três respostas tiveram `done_reason=stop`. O agente concluiu a resposta dessa
variante, enquanto os dados e o texto declaram contagem parcial. Evidências:
`count-fixed-ollama.json`, `count-fixed-ollama-responses.json`,
`f0ed0aa7d6ad497d8a92bc01d7ba26d7.json`. A variante não é a rota curta sem modelo.

Um primeiro harness de leitura das evidências usou a codificação padrão do Windows
e corrompeu “Olá”; o matcher não reconheceu o pedido e o cliente sem modelo
levantou AssertionError. A leitura foi corrigida para UTF-8 e a execução seguinte
passou. O artefato inicial foi preservado em `count-fixed-filesystem-initial.json`.

## Checks finais

Com `.venv\Scripts\python.exe`:

- `-m pytest -q -p no:cacheprovider`: **104 aprovados, 12 ignorados**, 4 avisos de
  depreciação do LanceDB. Dez ignorados porque NiceGUI não está instalado nessa
  `.venv`; dois por indisponibilidade de criação de symlinks no Windows.
- `-m mypy aether`: aprovado, 27 arquivos.
- `-m ruff check aether tests scripts`: aprovado; avisos de acesso negado aos
  diretórios já registrados, sem modificar suas permissões.
- `scripts/verify.py`: saída **0**, unittest, pytest, mypy, Ruff e compilação/TOML
  aprovados. JSON detalhado: `2757b345efb9496cadd550ec4dfb9274.json`;
  log: `count-verify-final.log`. O verify não executa inferência real; as
  integrações reais acima são verificações separadas.

No Python global, que tem NiceGUI instalado:
`python -m unittest discover -s tests -p test_gui_runtime.py -v`: **10 testes
aprovados**, usando componentes reais do NiceGUI e backends controlados.
Cobrem controles, resposta assíncrona, cancelamento, resultado ausente, erro do
backend/renderizador, saída excessiva e contagem parcial. Log:
`count-gui-runtime-tests-final.log`. Não constituem teste visual de janela nativa
nem execução real do Ollama pela janela.

## Pendências

A causa da interrupção histórica não pode ser recuperada dos registros antigos.
Se repetir, a GUI e os novos JSON agora registram o motivo específico.
Os 20 caminhos inacessíveis impedem afirmar total completo; ACLs não foram
alteradas e os diretórios não foram silenciosamente excluídos. A abertura da GUI
foi informada pelo usuário; não houve nova observação visual da janela nativa
nesta etapa. NiceGUI/pywebview permanecem no ambiente global, e não na `.venv`.
