# Interface desktop — PySide6

Janela única, minimalista, que reaproveita `analisador_projeto` e
`orquestrador` como bibliotecas Python (não via CLI):

```
┌──────────────────────────────────────────────────────┬─────────────┐
│ Pasta do projeto [___] [Procurar…] [Abrir ZIP…]       │ Diagnóstico │
│                  [Gerar mockup simples…]              │ (dockável,  │
│ [Analisar projeto] [Usar pasta extraída mesmo assim]  │  arrastável)│
│ [Descrever mockup…]  (status da descrição)            │             │
│                                                        │             │
│ Instrução                                             │             │
│ ┌────────────────────────────────────────────────────┐│             │
│ │                                                      ││             │
│ └────────────────────────────────────────────────────┘│             │
│ [Executar]                                            │             │
│ (status)                                              │             │
├────────────────────────────────────────────────────────────────────┤
│ Progresso (dockável, arrastável)                                    │
│ (log ao vivo do orquestrador / da importação de ZIP / do mockup)    │
└──────────────────────────────────────────────────────────────────��─┘
```

"Diagnóstico" e "Progresso" são painéis Qt dockáveis (`QDockWidget`) —
arraste pela barra de título deles para reposicionar, empilhar,
flutuar como janela solta, ou fechar. O arranjo que o usuário montar
fica salvo (`QSettings`) e volta na próxima abertura.

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
"Instrução" já tiver texto, cada linha vira o rótulo de um elemento; caso
contrário usa uma lista padrão. O PNG gerado fica num diretório
temporário, e "Descrever mockup…" já abre o diálogo de escolha de imagem
nessa mesma pasta — fecha o ciclo gerar → descrever → usar como contexto
no "Executar".

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
