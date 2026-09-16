# Interface desktop — PySide6

Janela única, minimalista, que reaproveita `analisador_projeto` e
`orquestrador` como bibliotecas Python (não via CLI):

```
┌──────────────────────────────────────────────────────┐
│ Pasta do projeto  [________] [Procurar…] [Abrir ZIP…] │
│ [Analisar projeto] [Usar pasta extraída mesmo assim]  │
│                                                        │
│ Diagnóstico                                           │
│ ┌────────────────────────────────────────────────────┐
│ │ (texto do analisador_projeto)                       │
│ └────────────────────────────────────────────────────┘
│                                                        │
│ Instrução                                             │
│ ┌────────────────────────────────────────────────────┐
│ │                                                      │
│ └────────────────────────────────────────────────────┘
│ [Executar]                                            │
│                                                        │
│ Progresso                                             │
│ ┌────────────────────────────────────────────────────┐
│ │ (log ao vivo do orquestrador / da importação de ZIP)│
│ └────────────────────────────────────────────────────┘
│ (status)                                              │
└────────────────────────────────────────────────────────┘
```

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
