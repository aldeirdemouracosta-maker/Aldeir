# Entrega local — base desktop adaptada, 10/10/2026

## Estado

Implementação preparada para revisão no worktree `linux-checkout`, branch
`linux/fabrica-ubuntu`, baseada em `origin/claude/friendly-rubin-xg4c53`
(`3b139233f2c70e5c0869849b7d47523fe41e9ec4`). Alterações locais não commitadas;
nenhum push, instalação/desinstalação real ou mudança da instalação Windows.
Ainda **não é uma release homologada no Ubuntu**. A comparação de candidatos,
ponto de entrada e instruções estão em README_UBUNTU.md.

## Alterações para revisão

| Arquivo | Mudança |
|---|---|
| interface/janela_principal.py | Consulta assíncrona de modelos, seleção obrigatória, chat/histórico, aprovação por ação, editor manual, estado de execução, foco/rótulos/atalhos, rolagem/layout e fontes instaladas |
| interface/servidor_local.py (novo) | Validação de URL local e consulta real de IDs em /v1/models |
| orquestrador/orquestrador.py | Endpoint/modelo configuráveis (também CLI), extração estrita, pedidos explicativos, confirmação de resultados, loop/progresso, histórico e resultados completos |
| compat_proxy.py (novo) | Adapta as ferramentas portuguesas ao núcleo corrigido existente |
| fabrica_correcoes/ (novo) | Núcleo do proxy, testes e inicialização de pacote; a lógica do proxy não foi reimplementada |
| sandbox_execucao/executar_sandbox.py | Importação tolerante a ausência de resource para testes Windows; comandos continuam recusados sem POSIX/bwrap |
| empacotamento/usuario.py (novo) | Cópia local, venv, atalho, diagnóstico e remoção seletiva por hash dentro do diretório do usuário |
| empacotamento/instalar.sh, desinstalar.sh | Substituição da exigência de root por entradas do instalador por usuário |
| empacotamento/iniciar.sh, diagnosticar.sh (novos) | Abertura do checkout e diagnóstico somente de leitura |
| tests/test_ubuntu_adaptacoes.py (novo) | Doze casos com intenção de ação, seleção, erro, teclado, escrita/recusa, editor, confinamento, loops e preservação |
| tests/test_interface.py, test_orquestrador.py | Adaptação das expectativas de segurança e controles novos; retirar skips globais de fluxos independentes de bubblewrap |
| tests/test_buscar_codigo.py | Comparação de caminhos independente do separador do sistema |
| validar_interface_real.py (novo) | Execução opt-in de pedido explicativo via janela Qt e servidor real, isolando QSettings/evidências |
| .gitignore, .gitattributes | Venv/evidências/temporários ignorados e scripts com LF |
| README_UBUNTU.md, VALIDACAO_UBUNTU.md | Base, comandos, evidências e pendências |

No checkout original, somente a documentação desta reavaliação foi atualizada
(PESQUISA_LINUX.md, README.md e VALIDACAO.md). Código e evidências anteriores do
pacote fabrica-correcoes permaneceram preservados.

O SHA-256 de fabrica-correcoes/fabrica_proxy.py e da cópia
linux-checkout/fabrica_correcoes/fabrica_proxy.py é idêntico:

```text
7daeae1942e5b2ea914aa3a69371f4957c0f55af9cc93915037e06dd4adbad4c
```

## Testes locais executados

Ambiente Windows, Python 3.13.15, PySide6 6.12.0, pytest 9.1.1,
pytest-qt 4.5.0; dependências em .venv do checkout, sem instalação global.

```text
QT_QPA_PLATFORM=offscreen python -B -m pytest -q
218 passed, 15 skipped in 33.06s

python -B -m unittest discover -s fabrica_correcoes -q
Ran 39 tests in 2.135s — OK

Pacote original, diretório ../fabrica-correcoes:
python -B -m unittest -q
Ran 66 tests in 2.438s — OK
```

As suítes se sobrepõem no núcleo do proxy; os números não devem ser somados
como testes únicos. Quinze casos dependentes de bubblewrap ficaram pulados.
As primeiras execuções foram bloqueadas pelo sandbox em arquivos temporários;
foram repetidas com permissão fora dele. Uma falha de comparação de separador
Windows no teste herdado foi corrigida para as_posix().

Os testes Qt exercitam janela, botões, QThread e mensagens com HTTP falso,
escrevendo/recusando arquivos reais em pastas temporárias, incluindo espaços e
acentos. A recusa simulada do diálogo volta como erro, o arquivo fica ausente e
finalizar não pode indicar sucesso. Editor manual abre/salva UTF-8, recusa mantém
o conteúdo e ../ é bloqueado. Remoção seletiva foi testada somente em diretório
temporário, preservando ajuste posterior e arquivo novo. Tab e Ctrl+Return foram
verificados; leitor de tela real não foi validado. O teste de pressionar Ctrl+Enter
encontrou uma falha do atalho padrão no Qt offscreen; foi corrigida com filtro
de eventos do campo de mensagem. A suíte de adaptações passou após a correção:
12 passed in 2.10s. A suíte completa foi repetida após esse último ajuste.

Passaram também bash -n dos quatro scripts (Git Bash, apenas sintaxe) e
git diff --check. Git Bash não é um ambiente Ubuntu. A sintaxe Python é compatível
com a gramática 3.10; a execução efetiva foi em Python 3.13.

## Interface adaptada com Ollama real

O diagnóstico somente de leitura consultou `/v1/models`:
`nomic-embed-text:latest`, `qwen3:8b`. Foi escolhido qwen3:8b após comprovar
sua disponibilidade, sem fallback silencioso. O teste foi em Qt **offscreen no
Windows**, com QSettings isolado, sem abrir FabricaApp.exe instalado.

Executado duas vezes com `validar_interface_real.py`: 54.46s e 26.51s. Ambas
receberam resposta explicativa do Ollama, nenhuma ferramenta foi executada e
exemplo.py permaneceu ausente. As evidências em
`evidencias-local/ollama-ui-01/resultado.json` e `ollama-ui-02/resultado.json`
contêm modelos consultados, pedido, resposta, status e tempo. São ignoradas
pelo Git. A segunda captura em `janela-offscreen-windows.png` comprovou rótulos
legíveis após carregar a fonte instalada (Qt offscreen inicialmente não
enumerava fontes). Posteriormente o painel Progresso passou a ser trazido à
frente ao enviar, para a conversa aparecer mesmo se Relatórios estava selecionado;
essa mudança passou na suíte Qt. Capturas são evidência de renderização offscreen
Windows, não de aparência no Ubuntu.

Diagnóstico: PySide6 disponível, bubblewrap ausente. Ollama responde em 11434.
O proxy antigo em 11435 responde aos modelos, mas `/saude` retorna 404; o novo
diagnóstico não o declara saudável apenas por ter porta/API abertas. Ele não foi
substituído nem encerrado.

Configuração real Windows ao final manteve SHA-256 igual à validação anterior:

```text
0294f66dc4f93d1d0e2bc9f38a3baa0cc663697b762c35bb99dab599cebbae07
```

## Pendências e limites

- Não há distribuição Ubuntu utilizável identificada no ambiente. Não foram
  executados instalação real, .desktop, abertura com display, comandos isolados,
  login ou remoção no Ubuntu. Procedimento reproduzível em README_UBUNTU.md.
- Testar bubblewrap e políticas de namespaces/AppArmor em Ubuntu real. O programa
  informa falha e nunca troca para execução sem isolamento.
- Testar teclado completo, foco em diálogos, leitor de tela e aparência Qt/XCB
  no Ubuntu; teste offscreen não substitui esses resultados.
- Validar com IA real os fluxos de edição/comando/reteste desta base. Esses fluxos
  passaram com HTTP simulado e ferramentas locais; o teste Ollama desta entrega
  cobriu o pedido explicativo. As cinco evidências reais anteriores do proxy
  permanecem válidas para seu executor de teste, não comprovam o executor Ubuntu.
- Histórico do chat é em memória; não é restaurado após fechar. O modelo tem
  limite de tokens/contexto e erros de truncamento continuam possíveis.
- Últimas escritas falhas são verificadas por caminho; afirmações textuais usam
  heurísticas conservadoras do núcleo do proxy. Não há prova semântica de tarefa
  concluída apenas por uma ferramenta retornar sucesso.
- Confirmar correspondência com o aplicativo Windows e licença de distribuição
  desta base. Nenhum pacote .deb/AppImage foi produzido ou publicado.
