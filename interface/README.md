# Interface desktop — PySide6

Janela única, minimalista, que reaproveita `analisador_projeto` e
`orquestrador` como bibliotecas Python (não via CLI):

```
┌──────────────────────────────────────────────────────┬─────────────┐
│ Pasta do projeto [___] [Procurar…] [Abrir ZIP…]       │ Diagnóstico │
│                  [Gerar mockup simples…]              │ ou Código   │
│ Elementos do mockup simples (opcional)                │ (abas,      │
│ ┌────────────────────────────────────────────────────┐│  dockável,  │
│ [Analisar projeto] [Usar pasta extraída mesmo assim]  │  arrastável)│
│ [Descrever mockup…]  (status da descrição)            │             │
│                                                        │             │
│ Instrução      [Exemplos de instrução… ▾]             │             │
│ ┌────────────────────────────────────────────────────┐│             │
│ │                                                      ││             │
│ └────────────────────────────────────────────────────┘│             │
│ [Executar] [Parar] [Configurar busca semântica…]      │             │
│ [Configurar microagente…]                             │             │
│ [Configurar analisador de erros…]                     │             │
│ [Verificar configuração da GPU]                       │             │
│ [Encerrar todos os llama-server]                      │             │
│ (status)                                              │             │
├────────────────────────────────────────────────────────────────────┤
│ Progresso ou Relatórios (abas, dockável, arrastável)                │
│ (log ao vivo / histórico de erros por execução)                    │
└──────────────────────────────────────────────────────────────────��─┘
```

"Diagnóstico", "Progresso", "Código" e "Relatórios" são painéis Qt
dockáveis (`QDockWidget`) — nascem em abas (`tabifyDockWidget`),
arraste pela barra de título pra reposicionar, empilhar, flutuar como
janela solta, ou fechar. O arranjo que o usuário montar fica salvo
(`QSettings`) e volta na próxima abertura.

**"Código"** mostra o conteúdo de cada `escrever_arquivo` formatado de
verdade (quebra de linha real, com o nome do arquivo no título do
painel) — a mesma informação já aparece em "Progresso", só que ali vem
como uma linha só de JSON com `\n` escapado, difícil de ler.

**"Relatórios"** acumula erros entre execuções — ao contrário de
"Progresso" (limpo a cada "Executar"), esse painel **não é limpo**:
registra, com hora e a última ferramenta chamada, toda falha de
`executar_comando` (código de saída != 0, com um trecho do `stderr`),
todo `erro: ...` de `ler_arquivo`/`escrever_arquivo`/`buscar_codigo`, e
toda exceção/interrupção da execução — histórico rápido de "o que deu
errado e onde", sem precisar reler o log inteiro de cada rodada.

## Por que roda em thread separada

Uma chamada real ao modelo pode levar minutos (visto na prática:
hardware sem AVX2 + GPU híbrida). `TrabalhadorAnalise` e
`TrabalhadorOrquestrador` (`QObject` + `QThread`) rodam a análise e o
orquestrador fora da thread principal — a janela nunca trava enquanto
espera resposta, e o `on_evento` do orquestrador (ver
`orquestrador/README.md`) alimenta o painel de progresso ao vivo via
sinal Qt, linha por linha, conforme cada ferramenta é chamada.

## Uso

```bash
pip install -r requirements.txt
python3 -m interface.janela_principal
```

Fluxo: escolher a pasta do projeto (ou importar um `.zip`, ver abaixo)
→ "Analisar projeto" (preenche o diagnóstico e já fica disponível como
contexto) → escrever a instrução → "Executar". O botão fica
desabilitado durante a execução; o painel de progresso mostra cada
chamada de ferramenta e o resultado.

Clicar em "Executar" sem ter rodado "Analisar projeto" antes não é
bloqueado, mas mostra um aviso no painel de progresso — sem diagnóstico
como contexto, o modelo tende a chutar a estrutura do projeto (visto na
prática: um resumo citando arquivos que não existiam na pasta certa).

O menu **"Exemplos de instrução…"** ao lado do rótulo "Instrução" tem
alguns pontos de partida prontos (`EXEMPLOS_INSTRUCAO`, em
`janela_principal.py`) — escolher um substitui o texto atual do campo e
o menu volta pro placeholder, pronto pra escolher outro em seguida.

O botão **"Parar"** (ao lado de "Executar", habilitado só durante uma
execução) pede pro orquestrador parar antes da próxima chamada ao
modelo ou ferramenta — não cancela uma chamada já em andamento (isso
exigiria cancelar uma requisição HTTP ou matar um processo de sandbox
no meio), só evita começar a próxima rodada. Existe porque, na prática,
um modelo pequeno pode entrar num padrão de "correção" ruim (ex.:
reescrever um arquivo inteiro repetidamente tentando "consertar" um
falso positivo do diagnóstico) e antes não havia como interromper sem
fechar a janela inteira.

O botão **"Configurar busca semântica…"** aponta o executável
`llama-server` e o GGUF de um modelo de embeddings (ver
`busca_codigo/README.md`) — sempre pede os dois arquivos de novo a
cada clique, não reaproveita um caminho salvo (evita repetir o bug do
caminho de visão que travava). Opcional: sem configurar, "Executar"
funciona normalmente, só sem a ferramenta `buscar_codigo` disponível
pro agente.

O botão **"Configurar microagente…"** aponta o executável `llama-server`
e o GGUF de um modelo pequeno (ex.: `Qwen2.5-Coder-0.5B`, ver
`microagentes/README.md`) — mesmo padrão do "Configurar busca
semântica…": sempre pede os dois de novo a cada clique. Opcional: sem
configurar, "Executar" funciona normalmente, só sem a ferramenta
`delegar_tarefa` disponível pro agente principal delegar sub-tarefas
pequenas a um modelo mais leve.

O botão **"Configurar analisador de erros…"** é o par oposto: aponta
o `llama-server` e o GGUF de um modelo de **raciocínio** (ex.:
`MiniCPM5-1B`, ver `microagentes/README.md`) — habilita a ferramenta
`analisar_erro`, que o agente principal usa pra diagnosticar a causa
de um erro antes de tentar corrigi-lo. Mais lento de propósito
(prioriza precisão), independente do "Configurar microagente…" — os
dois podem estar configurados ao mesmo tempo, com modelos diferentes,
cada um pro seu papel.

O botão **"Verificar configuração da GPU"** lista (via
`motor_ia.listar_processos_llama_server`, lendo `/proc` — Linux) todo
processo `llama-server` rodando agora e avisa, no painel "Relatórios",
se algum foi iniciado **sem** `-ngl`/`--n-gpu-layers`. Também mostra a
temperatura atual da GPU (via `motor_ia.temperatura_gpu_celsius`,
sysfs), quando o sistema expõe o sensor. Existe porque o servidor do
modelo de código é subido manualmente pelo usuário, fora do controle
da Fábrica — nada no código impede rodar sem limite de GPU, e isso já
derrubou uma GPU sob carga sustentada numa sessão real (ver
`TESTE_LOCAL.md`). Esse botão só torna o problema visível, não o
resolve sozinho.

O botão **"Encerrar todos os llama-server"**, ao lado, é o
complemento que age sobre o aviso: manda `SIGTERM` (via
`motor_ia.encerrar_processos_llama_server`) em todo processo listado
acima — pede confirmação antes (`QMessageBox`), porque isso inclui
qualquer servidor de código ou visão que o usuário tenha subido
manualmente, e derruba na hora qualquer execução em andamento no
aplicativo. Pensado como botão de emergência (ex.: GPU sem limite +
temperatura alta ao mesmo tempo), não como parte do fluxo normal.

## Abrir um projeto em ZIP

"Abrir ZIP…" usa `importador_zip/inspecionar_zip.py` (o mesmo portão
de segurança testado em `tests/test_importador_zip.py`) via
`TrabalhadorImportacaoZip`, também em `QThread` própria — extração e
varredura de um ZIP grande não trava a janela. O ZIP é extraído para
um diretório temporário isolado (`tempfile.mkdtemp`), nunca sobre o
projeto atual.

- **ZIP sem arquivos de risco ou padrões suspeitos**
  (`pode_auto_prosseguir=True`): a pasta extraída já é usada
  automaticamente — preenche "Pasta do projeto" e mostra
  "ZIP importado — sem riscos detectados."
- **ZIP com itens sinalizados** (nome/extensão de risco, ou padrão de
  comando perigoso encontrado no conteúdo): a pasta **não** é
  preenchida sozinha. O painel de progresso lista cada achado
  (arquivo e motivo) e aparece o botão "Usar pasta extraída mesmo
  assim" — só depois de revisar o log e clicar nele é que a pasta vai
  para "Pasta do projeto".
- **ZIP inseguro** (zip slip, caminho absoluto, link simbólico, ou
  zip bomb por tamanho/razão de compressão): `extrair_seguro` recusa a
  extração inteira antes de gravar qualquer arquivo — a UI mostra o
  erro no painel de progresso e a pasta do projeto continua vazia.

## Gerar um mockup simples (sem IA)

"Gerar mockup simples…" desenha um wireframe genérico local via
`geracao_mockup/gerar_mockup_simples.py` — retângulos rotulados (campos,
botões, listas) desenhados com `QPainter`, sem nenhum modelo de IA e sem
custo de GPU/VRAM, instantâneo. Serve como ponto de partida rascunhado
quando ainda não existe nenhuma imagem de mockup de verdade: se o campo
"Elementos do mockup simples" (separado da "Instrução" — um serve pra
descrever o wireframe, o outro é a instrução em linguagem natural pro
orquestrador; eram o mesmo campo antes e misturavam os dois propósitos)
tiver texto, cada linha vira o rótulo de um elemento; caso contrário usa
uma lista padrão. O PNG gerado fica num diretório temporário, e
"Descrever mockup…" já abre o diálogo de escolha de imagem nessa mesma
pasta — fecha o ciclo gerar → descrever → usar como contexto no
"Executar".

Ao lado do PNG, também é salvo um JSON (mesmo nome, extensão `.json`,
via `caminho_layout_json`) com a posição/tamanho exatos de cada
elemento — a mesma geometria usada para desenhar, que senão seria
perdida ao virar só uma imagem. Um agente que for gerar a interface real
a partir desse mockup pode ler esse JSON diretamente em vez de precisar
extrair coordenadas de uma descrição em texto livre do modelo de visão.

Para um mockup desenhado à mão com mais controle (não um rascunho
automático), veja a avaliação do Penpot em
`PESQUISA_FERRAMENTAS_UIUX_OPENSOURCE.md` — self-hosted, fora deste
repositório.

## Descrever um mockup (modelo de visão)

"Descrever mockup…" liga `visao_mockup/interpretar_mockup.py` (agente
reduzido, validado contra Qwen2.5-VL-7B numa RX 580 — ver
`TESTE_LOCAL.md`, seção 11) à interface via `TrabalhadorDescricaoMockup`,
também em `QThread` própria. Fluxo: escolhe a imagem do mockup, depois
(só na primeira vez — fica salvo em `QSettings`) o executável
`llama-server`, o modelo de visão e o `mmproj`, ambos em GGUF. A
descrição gerada some com o diagnóstico como contexto extra ao clicar
"Executar" — mesmo padrão de `--contexto-arquivo` + `--diagnostico` na
CLI do orquestrador.

Importante: o servidor de visão e o servidor de código não cabem
juntos em 8GB de VRAM — desligue o modelo de código antes de clicar
"Descrever mockup…", e religue-o antes de "Executar". A interface não
gerencia essa troca sozinha (mesma decisão de arquitetura documentada
em `TESTE_LOCAL.md`).

## Como foi testado sem tela

Este ambiente de desenvolvimento não tem display real. Os testes
(`tests/test_interface.py`) rodam com `QT_QPA_PLATFORM=offscreen` —
Qt real, `QThread` real, sinais reais, só sem renderizar pixels — e
exercitam a janela de ponta a ponta: preencher o campo de pasta,
clicar nos botões de verdade (`.click()`), esperar a thread de fundo
terminar (`qtbot.waitUntil`), e conferir tanto o texto que aparece nos
painéis quanto o arquivo real escrito em disco pelo
`TrabalhadorOrquestrador` (via um servidor OpenAI-compatible falso,
mesmo padrão usado em `tests/test_orquestrador.py`).

## Limites atuais

- Um projeto por vez, uma execução por vez (like `orquestrador`).
- Sem histórico entre execuções — cada clique em "Executar" começa do
  zero.
- Diagnóstico rodado sem a suíte de testes do projeto
  (`rodar_testes_automaticos=False`) para a UI responder rápido; a CLI
  (`--diagnostico`) roda com testes.
