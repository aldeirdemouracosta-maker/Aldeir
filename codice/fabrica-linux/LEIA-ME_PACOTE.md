# Entrega de fontes Linux — guia curto

Esta entrega contém a base desktop adaptada, scripts e testes. **Ubuntu ainda
não foi validado**; os resultados existentes são Windows/Qt offscreen. Não é
um .deb/AppImage nem inclui dependências pré-instaladas. Consulte README_UBUNTU.md
e VALIDACAO_UBUNTU.md para detalhes e a pendência da licença de distribuição.

## Dependências

- Ubuntu com sessão gráfica; Python 3.10+, venv e pip.
- PySide6>=6.7, instalado pelo requirements.txt; rede para baixar seus wheels.
  Bibliotecas Qt/XCB/OpenGL e fontes do sistema precisam estar disponíveis.
  Em Ubuntu desktop, confira especialmente libxcb-cursor0 e uma fonte como
  fonts-dejavu-core. Bibliotecas adicionais dependem da instalação Ubuntu.
- bubblewrap (`bwrap`) para comandos isolados; namespaces de usuário/rede precisam
  ser permitidos. Sua ausência não habilita execução sem isolamento.
- Ollama já instalado/iniciado com um modelo de geração disponível, ou outro
  servidor local compatível com OpenAI. Não há modelo fixo nem download automático.
- Testes: pytest>=8 e pytest-qt>=4.5 (requirements-dev.txt). Os testes de sandbox
  usam ferramentas do sistema, incluindo curl e git. Os dois testes do analisador
  precisam de pytest no `python3` acessível **dentro** do sandbox; instalar somente
  no venv do aplicativo não garante isso. O pacote Ubuntu python3-pytest atende
  essa dependência quando `/usr/bin/python3` é o interpretador utilizado.
- Opcional: llama-server e modelos GGUF para visão, busca semântica e microagentes.

Dependências de sistema devem estar provisionadas. Se necessário, um administrador
pode instalar python3-venv, bubblewrap, libxcb-cursor0, fonts-dejavu-core,
python3-pytest, curl e git. A instalação **do aplicativo** abaixo não usa sudo.

## Extrair, conferir e testar

Coloque o arquivo e seu .sha256 no mesmo diretório no Ubuntu. Os comandos partem
desse diretório; a pasta de extração é nova para não misturar instalações:

```sh
sha256sum -c fabrica-linux-ubuntu-2026-10-10.tar.gz.sha256
mkdir -p "$HOME/Fabrica entrega"
tar -xzf fabrica-linux-ubuntu-2026-10-10.tar.gz -C "$HOME/Fabrica entrega"
cd "$HOME/Fabrica entrega/fabrica-linux-ubuntu"
sha256sum -c CONTEUDO.sha256
./empacotamento/diagnosticar.sh

python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt -r requirements-dev.txt
QT_QPA_PLATFORM=offscreen .venv/bin/python -B -m pytest -q -rs
.venv/bin/python -B -m unittest discover -s fabrica_correcoes -q
./empacotamento/diagnosticar.sh
./empacotamento/iniciar.sh
```

O último comando abre a interface do checkout na sessão gráfica real. Na janela,
informe o servidor (Ollama normalmente http://127.0.0.1:11434/v1), clique
Consultar modelos, selecione um ID consultado e escolha uma pasta de teste com
espaços. Verifique chat explicativo sem execução, escrita aprovada/recusada,
edição manual, comandos, correção/reteste, loop e navegação por teclado.

Para instalar uma cópia independente no usuário e gerar o atalho:

```sh
./empacotamento/instalar.sh
"${XDG_DATA_HOME:-$HOME/.local/share}/fabrica-local-ia/iniciar.sh"
```

Também pode abrir **Fábrica Local de IA** no menu de aplicativos. A instalação
fica no diretório do usuário e baixa PySide6 em seu próprio venv. Destino ou
atalho existentes são preservados e causam recusa de sobrescrita.

Feche a janela. Para diagnosticar e desinstalar a cópia instalada:

```sh
cd "${XDG_DATA_HOME:-$HOME/.local/share}/fabrica-local-ia"
.venv/bin/python -B -m empacotamento.usuario diagnosticar
python3 -B -m empacotamento.usuario remover
```

A remoção é seletiva por hash: preserva arquivos modificados/novos, projetos,
QSettings, manifesto e resíduos do venv. Não use remoção recursiva para limpar
esses resíduos sem revisá-los. Ela não remove o checkout extraído.

## Os 15 testes pulados no Windows

Foram pulados por falta de bubblewrap/Linux, não por terem passado. No Ubuntu,
`pytest -q -rs` mostra qualquer skip restante; ter bwrap instalado não prova que
a política de namespaces permite seu funcionamento.

| Arquivo | Casos pulados | O que verificam |
|---|---:|---|
| tests/test_sandbox_execucao.py | 10 | execução simples, persistência da escrita no projeto, bloqueio de rede, bloqueio de escrita fora de /work, timeout, ausência de bwrap, falha de montagem, comando inexistente, recusa sem inspeção liberada e execução após liberação |
| tests/test_orquestrador.py | 3 | execução real de comando, aviso ao falhar comando de rede e ausência desse aviso em falha de comando comum |
| tests/test_analisador_projeto.py::TestComSandboxReal | 2 | contagem de testes passando em projeto completo e contagem de falhas em projeto incompleto |

O módulo de sandbox tem um skip global herdado: também pulou casos de erro que
usam executável falso ou apenas validação de liberação. Eles continuam incluídos
no pacote e serão exercitados quando a condição global for satisfeita.

Último resultado do checkout: **218 passed, 15 skipped**; núcleo do proxy:
**39 testes OK**. A validação do pacote extraído é registrada no relatório de
empacotamento entregue ao lado do arquivo. Os 66 testes do pacote Windows/proxy
original não integram esta distribuição do aplicativo, embora tenham passado
na entrega anterior. Nada disso substitui execução no Ubuntu real.

## Conteúdo e exclusões

CONTEUDO.sha256 lista os hashes de todos os arquivos entregues, exceto ele próprio.
MANIFESTO_PACOTE.json registra tamanhos, hashes, modos e origem. Scripts .sh são
armazenados com modo 0755 e LF; módulos com shebang também são executáveis.
Demais arquivos ficam com modo 0644, diretórios com 0755, sem donos do Windows.

Não são entregues .git, .venv, caches, temporários, logs, evidências locais,
configurações pessoais, backups ou credenciais. Documentos históricos sobre
máquinas pessoais e arquivos de projetos Android também são omitidos. Os módulos
opcionais e o ícone necessário à interface permanecem incluídos.
