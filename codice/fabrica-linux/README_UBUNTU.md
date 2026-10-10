# Fábrica Local de IA — adaptação Ubuntu da base existente

## Base identificada e correção da pesquisa anterior

Base: branch remota `claude/friendly-rubin-xg4c53`, commit
`3b139233f2c70e5c0869849b7d47523fe41e9ec4`. Checkout de adaptação:
`C:\Projetos\Aldeir-Fabrica\linux-checkout`, branch `linux/fabrica-ubuntu`.
Nenhum arquivo do trabalho anterior de fabrica-correcoes foi substituído.

A pesquisa anterior descartou cedo demais esta candidata por nome/proveniência.
O usuário confirmou que a base está neste repositório; a comparação por conteúdo
justifica adaptar a Fábrica Local de IA. Não é uma reconstrução de outro agente.
Não foi comprovada equivalência de cada módulo com FabricaApp.exe 3.3.0.

| Candidata | Interface/entrada | IA e ferramentas | Evidência e conclusão |
|---|---|---|---|
| friendly-rubin, raiz do checkout | PySide6; `interface/janela_principal.py:main`, `JanelaPrincipal`; QThread e QSettings | `motor_ia/selecionar_motor.py`: Ollama, LM Studio, llama.cpp; `orquestrador/orquestrador.py`: ler/escrever/listar, executar comandos isolados, retornar resultados | Interface funcional de desenvolvimento local, seleção de pasta/ZIP e diagnóstico. ARQUITETURA_FABRICA_LOCAL_IA.md denomina o fluxo fábrica local de aplicativos. É a melhor correspondência funcional e a base escolhida conforme a confirmação do usuário. |
| Lumivox Android, raiz/main/ZIP | Projeto Gradle Android | Aplicativo Android; sem o fluxo desktop de agente desta candidata | O ZIP Android não é a interface desktop; a documentação usa Lumivox também como nome da arquitetura de fábrica. O nome não foi usado como exclusão automática. |
| zen-hypatia, `codice/aether` | `aether.gui.app:main`, NiceGUI/pywebview; manifesto `name=aether` | Ollama, agente, ferramentas e índice vetorial | Funcionalidades semelhantes, mas ponto de entrada, interface e manifesto próprios. Sem evidência melhor de ser a base do binário Fábrica; não foi renomeado/substituído. |
| sleepy-cori, `fabrica-livre` | Contrato e AgenteFalso | Eventos roteirizados | Sem núcleo/interface executável; não é base completa. |

Tecnologia desta base: Python e PySide6 (Qt); módulos de IA/arquivos usam
biblioteca padrão. Comandos exigem Linux/POSIX e bubblewrap; não existe fallback
para executar fora do isolamento. Busca semântica, visão e microagentes requerem
executável llama-server/modelos GGUF informados, e são opcionais.
Não há LICENSE identificada para esta base; a confirmação do usuário autoriza
este trabalho local, mas não estabelece licença de distribuição pública. Essa
pendência deve ser resolvida antes de publicar um pacote.

## Implementado neste checkout

- Consulta `/v1/models` em thread; seleção explícita de modelo disponível, sem
  fixar qwen3:8b ou selecionar embeddings silenciosamente. Servidor local editável.
- Chat com histórico em memória por projeto/servidor/modelo e resultados visíveis.
- Aprovação explícita para cada escrita/comando; recusa volta ao modelo como erro.
- Editor manual, abrir/criar/salvar arquivo relativo ao projeto, UTF-8 e proteção
  contra caminhos que escapem da raiz, inclusive por links simbólicos.
- Núcleo corrigido do proxy reaproveitado em `fabrica_correcoes/fabrica_proxy.py`,
  cópia idêntica do pacote existente. `compat_proxy.py` adapta nomes/argumentos
  portugueses sem duplicar a lógica de extração e repetição. Não requer processo
  proxy para essas proteções; aceita também endpoint de um proxy externo.
- JSON com prosa não vira ferramenta; pedidos explicativos bloqueiam chamadas
  nativas e fallback também no executor. Última escrita recusada/falha impede
  finalizar como sucesso. Mudança confirmada permite retestar; repetição sem
  progresso é bloqueada, além do limite global de iterações.
- Código só aparece como escrito após retorno `ok`; execução de comandos permanece
  em bubblewrap, com resultados stdout/stderr/exit code e erro claro quando ausente.
- Rótulos acessíveis, foco destacado, botões navegáveis pelo teclado, Ctrl+O para
  pasta e Ctrl+Enter para enviar. Servidor tem mnemonic Alt+S, consulta Alt+M.
- Instalação por usuário com venv e .desktop; remoção seletiva por hash preserva
  arquivos alterados, arquivos novos, projetos e QSettings. Não modifica Windows.

O proxy completo permanece compartilhável com Windows. A alteração de import de
`resource` permite testar janela/arquivos no Windows, mas comandos isolados desta
base exigem Linux e falham claramente fora dele. Não é uma migração da instalação
Windows 3.3.0, nem migra sua configuração pessoal.

## Instalar e abrir no Ubuntu

Requisitos: Ubuntu desktop, Python **3.10+**, módulo venv/pip, rede para baixar
PySide6, bibliotecas Qt/XCB e bubblewrap para executar comandos. A instalação do
aplicativo é sem sudo. Dependências de sistema ausentes precisam ser provisionadas
pelo administrador (por exemplo python3-venv, bubblewrap, libxcb-cursor0); não são
instaladas automaticamente. Políticas de user namespaces/AppArmor podem impedir
bubblewrap mesmo presente: testar antes de considerar comandos homologados.

Transfira este checkout modificado para Ubuntu: clonar somente a branch remota
não inclui as alterações locais não commitadas. Na raiz da cópia:

```sh
python3 --version
sh empacotamento/diagnosticar.sh
sh empacotamento/instalar.sh
"${XDG_DATA_HOME:-$HOME/.local/share}/fabrica-local-ia/iniciar.sh"
```

Ou abra **Fábrica Local de IA** no menu. O destino é
`${XDG_DATA_HOME:-$HOME/.local/share}/fabrica-local-ia`, validado dentro de HOME.
O instalador copia os módulos e cria venv; não depende do checkout permanecer
no mesmo lugar. Destino/atalho existentes não são sobrescritos. Falha parcial
mantém manifesto para revisão/remoção. Caminhos com espaços são argumentos
separados; o .desktop usa a sintaxe própria de Exec.
O escape segue a [especificação Desktop Entry](https://specifications.freedesktop.org/desktop-entry/latest/exec-variables.html);
caminhos do executável com `=` ou caracteres de controle são recusados.

Alternativa de desenvolvimento, sem instalação/atalho:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt -r requirements-dev.txt
sh empacotamento/iniciar.sh
```

Com Ollama já iniciado, use `http://127.0.0.1:11434/v1`, clique **Consultar
modelos**, escolha um ID listado e selecione sua pasta. Escreva a mensagem e
envie. Para exemplos sem executar, diga isso explicitamente. Revise os diálogos
de escrita/comando; recusar não cria o arquivo. O painel Código pode ser editado
manualmente; informe o caminho relativo e use Salvar código.

Para usar o proxy externo corrigido em outra porta livre, execute a partir desta
raiz (substitua ID_LISTADO pelo modelo consultado e evite porta já ocupada):

```sh
.venv/bin/python -B -m fabrica_correcoes.fabrica_proxy \
  --ollama http://127.0.0.1:11434 --porta 11436 --modelo-verificado ID_LISTADO
```

Informe `http://127.0.0.1:11436/v1` na interface e consulte os modelos. O processo
do proxy é manual; pare-o com Ctrl+C. O núcleo também funciona integrado sem ele.
O diagnóstico padrão consulta 11434/11435; para outra porta confira `/saude`
explicitamente. Não use uma porta aberta como prova de identidade.

Feche a interface antes de remover:

```sh
cd "${XDG_DATA_HOME:-$HOME/.local/share}/fabrica-local-ia"
.venv/bin/python -B -m empacotamento.usuario diagnosticar
python3 -B -m empacotamento.usuario remover
```

Remoção conserva manifesto, diretórios e symlinks do venv, além de arquivos
modificados/novos. Configuração Qt por usuário (`FabricaLocalIA/Interface`, via
QSettings) não é removida. Para reinstalar, revise os resíduos e escolha manter
ou mover a instalação antiga; o instalador não apaga dados para liberar destino.
Não forneça o diretório de um projeto pessoal como destino.

## Testes reproduzíveis e pendências

```sh
QT_QPA_PLATFORM=offscreen .venv/bin/python -B -m pytest -q
.venv/bin/python -B -m unittest discover -s fabrica_correcoes -q
sh empacotamento/diagnosticar.sh
# Com display real:
sh empacotamento/iniciar.sh
```

No display real, testar pasta com espaços/acentos; chat explicativo sem arquivos;
escrita aprovada e recusada; editor manual; comando como `["python3", "teste.py"]`;
falha/correção/reteste; repetição bloqueada; Tab/Shift+Tab, foco e leitor de tela.
Conferir .desktop com desktop-file-validate, login, namespaces do bubblewrap,
instalação sem sudo, ajustes posteriores e remoção em uma conta de teste.

O ambiente atual é Windows, sem Ubuntu utilizável. Testes Qt offscreen comprovam
fluxos da base em Windows, não aparência, leitor de tela, .desktop ou isolamento
Ubuntu. Consulte VALIDACAO_UBUNTU.md para resultados finais. Não foi gerado
AppImage/.deb nem declarada uma versão Ubuntu pronta.
