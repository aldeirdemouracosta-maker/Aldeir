# Aether

Agente de código local em Python 3.12+, com CLI, loop ReAct, ferramentas de
arquivo, indexação semântica via Ollama/LanceDB e habilidades locais. Modelos
precisam estar previamente disponíveis no daemon Ollama local. O Aether não
baixa modelos, não modifica pesos e não oferece fallback cloud.

## Uso

### Interface desktop (NiceGUI)

A interface opcional usa o mesmo AetherAgent e a configuração do projeto:

```powershell
.venv\Scripts\python.exe -m pip install ".[gui]"
.venv\Scripts\python.exe -m aether.gui.app --path .
```

O modo padrão abre uma janela desktop via pywebview. Para conferir o esqueleto
visual sem inferência ou ferramentas, use `--demo`. Para usar o navegador local
sem janela nativa, acrescente `--browser` (servidor em 127.0.0.1:8080).
O comando instalado `aether-gui` oferece as mesmas opções.

A GUI tem sidebar com projeto, modelo e skills, chat com scroll automático,
planos, cards de resultados de ferramentas e textarea com botão Enviar
(Ctrl+Enter). O agente roda em uma thread via NiceGUI run.io_bound; perguntas e
aprovações são respondidas no chat. Uma conversa executa uma tarefa por vez.
Nova conversa limpa o histórico. Fechar a sessão libera perguntas pendentes;
inferências já iniciadas terminam conforme os limites do cliente Ollama.

O terminal permanece desabilitado na GUI, inclusive se a configuração do projeto
o habilitar. As ferramentas de edição continuam disponíveis ao agente para as
tarefas solicitadas. Nenhum modelo é baixado automaticamente.

`aether/gui/styles.py` define os tokens do tema dark e as classes `message-user`,
`message-agent`, `tool-card` e `status-badge`. Usa Inter/Segoe UI e JetBrains
Mono/Consolas com fallback local, sem baixar fontes. NiceGUI e pywebview são extras
opcionais; a CLI continua funcionando sem eles.

Na validação mais recente, NiceGUI 3.18.0 e pywebview 6.2.1 importaram corretamente
no Python global 3.13; os extras ainda não estão no `.venv`. Nesse ambiente, use:

```powershell
python -m aether.gui.app --path .
```

O modo padrão força `native=True`. A opção explícita `--browser` não passa
`window_size`, pois esse parâmetro habilitaria modo nativo novamente no NiceGUI.
Foi corrigido o contexto do timer de scroll automático, que podia falhar ao
enviar uma mensagem de uma tarefa assíncrona sem slot atual da UI.

Os componentes reais do NiceGUI e o fluxo assíncrono do chat passaram em três
testes no Python global, usando respostas controladas do modelo. Eles não
substituem inspeção visual ou inferência real. A abertura nativa nesta sessão
ficou bloqueada por `PermissionError: [WinError 5] Acesso negado` na criação dos
pipes multiprocessing; o servidor NiceGUI também requer esses pipes para seu
pool de processos. Nenhuma proteção ou permissão foi alterada. Para validar a
janela, execute o comando acima em um terminal normal fora do executor restrito.

Gates de regressão no `.venv`: 89 aprovados e 5 ignorados (dois testes Windows
de symlink e três de NiceGUI ausente nesse intérprete), mypy, Ruff, compilação e
TOML aprovados. Evidências atualizadas em
`.aether/evidence/gui-native-validation-final.md`; a implementação anterior
permanece documentada em `.aether/evidence/gui-implementation-final.md`.

Com as dependências de produção declaradas em pyproject.toml já disponíveis:

```bash
aether index .
aether index . --force
aether search "como funciona a autenticação" --limit 8
aether status .
aether run "Revise o módulo indexer"
aether chat
```

Todos os comandos carregam aether.yaml do diretório selecionado. Index e status
recebem o caminho como argumento; os demais comandos oferecem --path. O caminho
do projeto precisa ser um diretório existente.

## Habilidades locais

A descoberta ocorre exclusivamente em:

```text
.aether/skills/<nome>/SKILL.md
.aether/skills/<nome>/aether.json
```

A descoberta lê apenas o frontmatter delimitado por `---`, com name e description.
Os nomes usam letras minúsculas, números e hífens, com até 64 caracteres, e devem
coincidir com o nome da pasta. O parser aceita um mapeamento YAML restrito de
strings: valores simples, aspas e blocos literais/folded; rejeita tags, aliases,
estruturas aninhadas e campos duplicados. Prefira description entre aspas.

```yaml
---
name: minha-skill
description: "Procedimento local para uma tarefa específica."
---
Leia os arquivos relevantes, mostre um plano e registre limitações.
```

Metadados do Aether ficam separados em aether.json:

```json
{
  "version": "1.0.0",
  "required_tools": ["read_file"],
  "os": ["windows", "linux", "darwin"],
  "network": false,
  "required_executables": [],
  "resources": []
}
```

Manifesto e instruções completas só são lidos na seleção. Ferramentas/executáveis
necessários ausentes, OS incompatível, estrutura inválida, recursos ausentes ou
excesso de tamanho bloqueiam a seleção. Referências Markdown, caminhos entre
crases e recursos declarados devem permanecer na pasta da skill. Links simbólicos
e junctions não são aceitos na árvore. Ler uma skill não executa scripts.

Skills não concedem ferramentas, rede ou permissões, nem alteram limites. A seleção
não habilita terminal desabilitado. Skills que exigem rede ficam bloqueadas nesta
etapa. Não existe instalador pela internet ou seleção automática de todas as skills.

```bash
aether skills
aether skill-show aether-investigar-projeto
aether run "Explique a arquitetura" --skill aether-investigar-projeto
aether run "Revise as verificações" --skill aether-quality-gates --skill aether-report-evidence
```

No chat, use `/skills`, `/skill aether-corrigir-bug`, ou `/skill clear`. A seleção
vale para as próximas tarefas desse chat até ser alterada. As instruções de uma
skill da tarefa anterior são removidas do prompt quando a seleção muda.

As cinco habilidades originais incluídas são:

- aether-investigar-projeto: arquitetura, dependências, comandos e distinção entre fatos e hipóteses.
- aether-corrigir-bug: reprodução, correção mínima, verificação e limitações.
- aether-quality-gates: baseline, comparação antes/depois e PASS/FAIL/BLOCKED/N/A.
- aether-report-evidence: resultados observados, JSON, resumo e redação de segredos.
- aether-revisar-diff: arquivos alterados, objetivo e preservação das mudanças anteriores.

Quality gates e report evidence são adaptações locais de procedimentos inspirados
nos contratos LVCP do usuário. Não representam uma engine LVCP instalada, nem
presumem executáveis ou resultados LVQA/VHQA.

## Ferramentas, planejamento e segurança

Permanecem disponíveis read_file, write_file, edit_file, list_dir,
get_project_structure, search_codebase, git_status, git_diff e ask_user. Há também
record_evidence para registrar BLOCKED ou N/A, com artefato e justificativa.

Caminhos resolvidos precisam permanecer na raiz, usando comparação estrutural.
Argumentos ausentes, desconhecidos, com tipos errados e tool calls malformadas
são rejeitados. edit_file exige uma única ocorrência exata do trecho antigo.
read_file limita o arquivo a 2 MiB e oferece intervalos de linhas.
Escritas de tools em metadados Git/agente e nas pastas de skills/evidências são
bloqueadas. Não há commit, push ou descarte automático. git_diff mostra alterações
não staged; revisão de alterações staged/untracked exige inspeção adicional.

O agente exige e mostra um plano antes das ferramentas, pergunta quando necessário
e continua com a resposta. Aprovação do plano é opcional. Há limites de iterações,
chamadas por resposta, passos totais, falhas, perguntas, contexto e saída. Contexto
é medido em caracteres do JSON, incluindo schemas; não é uma contagem de tokens.
Ao exceder os limites, a tarefa é interrompida com indicação de incompletude.

run_terminal usa uma lista de argumentos e shell=False. Ele fica desabilitado e
fora dos schemas por padrão. A opção allow_unisolated_terminal=true habilita
explicitamente execução com as permissões do processo, timeout e captura limitada.
Timeout, diretório de trabalho e worktree não constituem sandbox. O processo pode
acessar arquivos e rede ou criar descendentes; o timeout só encerra o processo
direto. Confinamento por resolução de caminhos não elimina corridas com troca
concorrente de links. Git exige .git como diretório interno; worktrees com metadados
externos não são suportados nesta versão.

## Evidências

Cada tarefa recebe um identificador. Nome, versão e hash das instruções das skills
selecionadas ficam registrados. Ao terminar, o agente exporta:

```text
.aether/evidence/<task_id>.json
.aether/evidence/<task_id>.txt
```

Execuções de run_terminal registram comando, código de saída, duração, ambiente,
artefato, fase e limitações. PASS exige saída zero observada; falha ou timeout é
FAIL; execução não realizada é BLOCKED. N/A exige justificativa. Se nenhum comando
de verificação ocorrer, há um registro BLOCKED explícito. O modelo não pode usar
record_evidence para inventar PASS. Não há alegação automática de validação humana.

Use artifact e phase=before/after nos comandos pertinentes para comparar estados.
O relatório identifica regressões, resoluções, resultados inalterados e falta de
baseline. A comparação usa artefato, comando e ambiente; não prova equivalência
completa de dependências ou cobertura de testes.

Os relatórios não capturam variáveis de ambiente completas nem o texto da tarefa
(só seu hash). Padrões comuns de credenciais são redigidos; essa proteção não
identifica todos os formatos de segredo. Evite emitir credenciais nos comandos.

## Indexação e cache

A indexação incremental compara hashes SHA-256 dos chunks e posições de linhas.
Arquivos modificados são reindexados, apagados são removidos e arquivos esvaziados
perdem seus chunks. Todas as alterações são preparadas antes de substituir o índice;
falhas de leitura, quantidade ou conteúdo dos embeddings preservam o índice anterior,
inclusive com --force. O staging usa memória proporcional ao índice completo.
Ao mudar modelo ou parâmetros do embedder, use --force para reconstruir o índice.

O cache SQLite persistente armazena apenas vetores e chaves, nunca cache semântico
de edições, comandos ou resultados de testes. A chave inclui hash do texto exato
enviado, modelo, digest, endpoint, dimensão, parâmetros e versão de processamento.
Se o digest estiver ausente ou indisponível, embeddings locais continuam funcionando,
mas não são reutilizados nem armazenados persistentemente nessa chamada.

Vetores com dimensão errada, zeros, valores não finitos, booleanos ou fora do intervalo
float32 são rejeitados. O cache tem métricas persistentes e por sessão, remoção dos
registros menos recentemente usados e limite do arquivo SQLite após cada operação.
Journals e espaço temporário do SQLite não são uma quota de disco ou sandbox.

```bash
aether cache-status
aether cache-clear
```

cache-clear invalida o cache de embeddings; não remove o índice ou força reindexação.
cache-status mostra os contadores persistentes; os contadores da sessão dessa CLI
começam em zero. index mostra também as métricas da sessão que gerou embeddings.

Ollama aceita somente HTTP em localhost, 127.0.0.1 ou ::1, sem credenciais, caminho
adicional, query ou fragmento. Clientes ignoram proxies do ambiente e redirecionamentos.
Nomes contendo cloud e metadados de roteamento remoto são rejeitados antes de inferência.
A configuração e o comportamento do daemon local continuam sob controle do usuário.

## Configuração de exemplo

```yaml
cache:
  enabled: true
  path: .aether/embeddings.sqlite3
  max_bytes: 134217728
skills:
  max_bytes: 65536
  max_skills: 100
  max_selected: 5
agent:
  max_iterations: 25
  max_tool_calls: 8
  max_tool_steps: 50
  max_tool_failures: 3
  max_context_chars: 48000
  max_tool_output_chars: 12000
  max_response_chars: 12000
  require_plan_approval: false
  allow_unisolated_terminal: false
  terminal_timeout: 30
```

## Verificação desta etapa

Em 10/10/2026, Python 3.13, sem modelos reais:

- Suíte unittest: 81 testes, 79 aprovados e 2 ignorados porque o Windows não permitiu
  criar symlinks. O ramo de rejeição de links também é testado com simulação determinística.
- Compilação dos 25 arquivos Python e parsing do TOML: aprovados.
- Mypy, Ruff e pytest: BLOCKED, módulos ausentes. A tentativa de obter dependências
  leves falhou. Nenhuma dependência pesada, modelo ou peso foi instalado/alterado.

```bash
python -m unittest discover -s tests -v
python -m mypy aether
python -m ruff check aether tests scripts
python scripts/verify.py
```

verify.py usa comandos reais, exporta JSON/resumo e retorna código 1 se algum gate
falhar ou ficar BLOCKED. Nunca transforma dependência ausente em PASS.

Pendente: executar mypy/Ruff/pytest com dependências disponíveis e validar a CLI,
Pydantic, HTTPX e o armazenamento LanceDB real. Indexação, cache, skills e agente
foram testados com armazenamento/clientes falsos e subprocessos locais pequenos.
As evidências desta etapa não afirmam validação humana ou integração com modelos reais.

## Diagnóstico de tarefas na GUI — atualização de 10/10/2026

A GUI usa o estado estruturado do agente para mostrar o motivo de uma execução
incompleta no cabeçalho e no chat. Timeout, limites de contexto, resposta,
iterações e ferramentas, chamadas inválidas, saída truncada, cancelamento e
exceções deixam um código e uma descrição. Input, envio, seleção de skills e
reinício são liberados no encerramento, inclusive quando ocorre falha de renderização.
As evidências JSON distinguem `task_outcome` do resultado dos comandos de verificação.
Uma tarefa somente de leitura pode concluir sem executar comandos de verificação.

O pedido “Olá, me diga quantos arquivos Python existem neste projeto” usa uma
contagem determinística de caminhos, sem inferência. Outros pedidos podem usar
a ferramenta `count_python_files`, que retorna dados estruturados. A contagem é
recursiva, de arquivos regulares com extensão `.py` (sem distinguir maiúsculas).
Exclui `.git`, `.venv`, `venv`, `__pycache__`, `.pytest_cache`, `.mypy_cache`,
`.ruff_cache`, `.cache` e os locais gerados conhecidos na raiz: `.buildtmp`,
`.tmp`, `.aether/evidence`, `.aether/lancedb`, `.aether/gui-install-tmp`.
Não segue links/junctions e preserva diretórios legítimos chamados `tmp`.
Caminhos inacessíveis são registrados; nesses casos o total é parcial.
O terminal do agente permanece desabilitado e as proteções de caminhos permanecem ativas.

A reprodução real anterior à correção com `qwen3:8b` concluiu em 187,49 segundos,
mas estimou 32 arquivos a partir da árvore textual. Não reproduziu a interrupção
histórica; as evidências antigas não registraram sua causa. Depois da correção,
a contagem real encontrou 46 arquivos acessíveis e 20 caminhos inacessíveis,
portanto não confirmou o total completo. Uma integração real adicional com
`qwen3:8b` chamou a nova ferramenta e informou a contagem parcial em 157,38 segundos.
Nenhum modelo foi instalado ou alterado.

Validação atual: pytest na `.venv` com 104 aprovados e 12 ignorados, mypy e Ruff
aprovados. Dez testes de componentes reais do NiceGUI passaram no Python global;
na `.venv` esses dez testes são ignorados porque NiceGUI está ausente (os outros
dois dependem de symlinks do Windows). A abertura da janela foi informada pelo
usuário; esta etapa validou os componentes e encerramentos, sem nova validação
visual da janela nativa. Relatório detalhado: `.aether/evidence/count-validation-report.md`.
