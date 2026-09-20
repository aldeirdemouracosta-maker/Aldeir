# Testar a fábrica local na sua máquina (Ubuntu, Xeon + RX 580)

Guia prático para rodar `motor_ia/`, `importador_zip/`,
`sandbox_execucao/` e `orquestrador/` de verdade, com um modelo de IA
real — algo que não é possível fazer no ambiente de nuvem onde este
código foi escrito (sem GPU).

## 1. Clonar o repositório e entrar na branch

```bash
git clone https://github.com/aldeirdemouracosta-maker/Aldeir.git
cd Aldeir
git checkout claude/friendly-rubin-xg4c53
```

## 2. Dependências de sistema

```bash
sudo apt update
sudo apt install -y bubblewrap mesa-vulkan-drivers vulkan-tools build-essential cmake git python3 libvulkan-dev spirv-headers
```

`glslc` (compilador de shaders, necessário para compilar o llama.cpp
com Vulkan) só existe nos repositórios do Ubuntu a partir da versão
**24.04**. Confira a sua versão com `lsb_release -a`:

- **Ubuntu 24.04+**: `sudo apt install -y glslc`
- **Ubuntu 22.04 (Jammy) ou anterior**: o pacote não existe — instale
  o SDK oficial da LunarG, que traz o `glslc` junto:

  ```bash
  wget -qO- https://packages.lunarg.com/lunarg-signing-key-pub.asc | sudo tee /etc/apt/trusted.gpg.d/lunarg.asc
  sudo wget -qO /etc/apt/sources.list.d/lunarg-vulkan-jammy.list http://packages.lunarg.com/vulkan/lunarg-vulkan-jammy.list
  sudo apt update
  sudo apt install -y vulkan-sdk
  ```

Confirme que `glslc` está instalado antes de seguir para o próximo
passo — sem isso, a compilação do llama.cpp falha com dezenas de
erros `Vulkan_GLSLC_EXECUTABLE-NOTFOUND` (achado testando numa máquina
Ubuntu 22.04 real):

```bash
which glslc && glslc --version
```

Confirme que a GPU aparece via Vulkan:

```bash
vulkaninfo --summary | grep deviceName
```

Se não aparecer nada, o kernel `amdgpu` deveria estar embutido em
kernels recentes do Ubuntu — confira `lsmod | grep amdgpu` e
`dmesg | grep amdgpu`.

## 3. Compilar o llama.cpp com Vulkan

A RX 580 (Polaris/gfx803) tem um bug conhecido
(`VK_ERROR_DEVICE_LOST`) em builds recentes do backend Vulkan do
llama.cpp — resolvido compilando da fonte com uma versão recente do
Vulkan SDK:

```bash
git clone https://github.com/ggml-org/llama.cpp.git
cd llama.cpp
cmake -B build -DGGML_VULKAN=ON
cmake --build build --config Release -j$(nproc)
cd ..
```

Se `VK_ERROR_DEVICE_LOST` aparecer ao rodar, veja as notas de
compatibilidade Polaris em
[andrewdhannah/vulkan-polaris-llama](https://github.com/andrewdhannah/vulkan-polaris-llama)
e [aivisionslab-studios/rx580-local-ai-guide](https://github.com/aivisionslab-studios/rx580-local-ai-guide)
(referenciados em `ARQUITETURA_FABRICA_LOCAL_IA.md`, seção 6.1).

Se a compilação falhar com dezenas de erros como:

```
Vulkan_GLSLC_EXECUTABLE-NOTFOUND -fshader-stage=compute ...
vulkan-shaders-gen: one or more shaders failed to compile
```

confirme primeiro que `which glslc` retorna um caminho (passo 2). Se
retornar, o problema é o CMake ter guardado `NOTFOUND` em cache de uma
configuração anterior — **sempre apague `build/` por completo antes de
reconfigurar**, um `cmake -B build` sozinho não re-detecta o `glslc`:

```bash
rm -rf build
cmake -B build -DGGML_VULKAN=ON
cmake --build build --config Release -j$(nproc)
```

## 4. Baixar um modelo GGUF pequeno para o primeiro teste

Um modelo 7-8B em Q4_K_M cabe inteiro nos 8GB de VRAM da RX 580. Para
programação, por exemplo (baixe de onde preferir — Hugging Face é a
fonte usual de GGUF):

```bash
mkdir -p ~/modelos
# exemplo: Qwen2.5-Coder-7B-Instruct em GGUF Q4_K_M
# coloque o arquivo .gguf baixado em ~/modelos/
```

## 5. Subir o servidor do llama.cpp

```bash
./llama.cpp/build/bin/llama-server \
  -m ~/modelos/SEU_MODELO.gguf \
  --port 8080 \
  --host 127.0.0.1 \
  --jinja \
  -ngl 20 \
  --ctx-size 4096
```

`-ngl`/`--ctx-size` **não são opcionais em GPUs mais antigas/sem
monitoramento de temperatura confiável** — sem limite de camadas
offloaded, o `llama-server` pode empurrar a GPU no máximo sob carga
sustentada. Visto na prática: uma RX 580 travando o driver
Vulkan e corrompendo o sistema numa sessão real. Comece conservador
(`-ngl 20`), suba aos poucos só monitorando temperatura (`CoreCtrl`,
`nvtop`), nunca sem limite nenhum. `visao_mockup` e `busca_codigo`
(que sobem seus próprios `llama-server` internamente) já usam esse
mesmo padrão conservador por default — e, além de limitar `-ngl`,
recusam subir o servidor na GPU se a temperatura já estiver acima de
90°C no momento (via sysfs, ver `motor_ia/README.md`).

Esse servidor manual, por ser subido fora do controle da Fábrica, não
tem essa checagem — é o motivo do botão "Verificar configuração da
GPU" (mostra a temperatura atual e se algum `llama-server` está sem
`-ngl`) e do botão de emergência "Encerrar todos os llama-server" na
interface (ver `interface/README.md`).

`--jinja` é obrigatório — ativa o processamento de chat template
necessário para o tool calling do orquestrador funcionar (sem isso o
modelo escreve texto comum em vez de uma chamada estruturada).

Deixe rodando num terminal separado.

### Alternativa leve: Qwen2.5-Coder-3B

O orquestrador fala com qualquer modelo via API compatível com OpenAI
— trocar de modelo **não exige nenhuma mudança de código**, só apontar
o `llama-server` pra outro GGUF. Se quiser um modelo mais leve (menos
carga na GPU, mais rápido, mais seguro dado o histórico de travamento
desta máquina), `Qwen2.5-Coder-3B` é a recomendação: mesma família do
`Qwen2.5-Coder-7B` já usado aqui (mesmo tokenizer, mesmo chat
template, mesmo comportamento de tool-calling já testado nesta
sessão — sem "manhas" novas pra descobrir), ~2GB de RAM em Q4_K_M,
65% no HumanEval, Apache-2.0.

```bash
# baixar (ajuste o repositório GGUF exato conforme disponibilidade no Hugging Face)
./llama.cpp/build/bin/llama-server \
  -hf Qwen/Qwen2.5-Coder-3B-Instruct-GGUF \
  --port 8080 --host 127.0.0.1 --jinja \
  -ngl 20 --ctx-size 4096
```

Outros candidatos avaliados (ver conversa/README para comparação
completa): `Phi-4-mini` (MIT, melhor nota de código da leva — 74%
HumanEval — mas família diferente, exige validar tool-calling do
zero) e `MiniCPM5-2B` (Apache-2.0, surpreendentemente forte pro
tamanho, mas menos testado com llama.cpp/tool-calling — antes de
trazer pra máquina local, vale validar numa GPU alugada por hora
(RunPod/Vast.ai) ou Colab gratuito).

### Alternativa para tool-calling mais confiável: Granite-4.2-3B

O orquestrador tem uma "mania" documentada: vários modelos pequenos
não respeitam `tool_choice=required` e devolvem texto comum em vez de
uma chamada de ferramenta estruturada — por isso existe o parser de
fallback `extrair_chamada_de_texto` em `orquestrador.py`. O
`Granite-4.2-3B` (IBM, Apache-2.0, GGUF disponível em 3B/8B/30B) é
anunciado com tool-calling "reasoning-augmented" como foco principal
do treino — candidato a reduzir a dependência desse fallback, mas
ainda não validado nesta máquina; troca é só apontar o `llama-server`
pro GGUF dele, mesma flag `--jinja` obrigatória:

```bash
./llama.cpp/build/bin/llama-server \
  -hf ibm-granite/granite-4.2-3b-GGUF \
  --port 8080 --host 127.0.0.1 --jinja \
  -ngl 20 --ctx-size 4096
```

Candidatos vistos e **não adotados** dessa leva, por motivo concreto:
`LFM2.5-2.6B` (Liquid AI) tem GGUF pronto, mas a licença ("LFM Open
License"/LFM1.0) tem restrição de faturamento pra empresas maiores —
foge do padrão Apache-2.0/MIT usado no resto do projeto; "Qwen3.5-2B"
e "Qwen3.5-4B" não foram confirmados — as fontes verificadas só
mostram variantes do Qwen3.5 bem maiores (27B pra cima), então esses
dois tamanhos específicos precisam de confirmação direta na fonte
antes de considerar.

## 6. Confirmar que o `motor_ia` detecta o motor

Em outro terminal, dentro do repositório `Aldeir`:

```bash
python3 motor_ia/selecionar_motor.py
```

Esperado: `"escolhido": "llama.cpp (Vulkan)"` com
`"base_url": "http://localhost:8080/v1"`. Se vier `"escolhido": null`,
o diagnóstico no JSON diz qual checagem falhou (Vulkan não detectado,
ou o servidor não respondeu em `:8080`).

## 7. Rodar o orquestrador contra um projeto de teste

```bash
mkdir -p /tmp/projeto_teste
echo "def soma(a, b):\n    pass" > /tmp/projeto_teste/app.py

python3 -m orquestrador.orquestrador /tmp/projeto_teste \
  "implemente a função soma em app.py para retornar a soma de a e b, e valide com python3 -c 'from app import soma; assert soma(2,3)==5'"
```

Com `--diagnostico`, o `analisador_projeto` roda antes e o agente já
recebe TODOs/funções incompletas/estado estimado como contexto:

```bash
python3 -m orquestrador.orquestrador --diagnostico /tmp/projeto_teste \
  "termine a implementação pendente"
```

Esperado: o orquestrador chama o modelo, o modelo decide ler `app.py`,
escrever a implementação, rodar o comando de validação em sandbox, e
chamar `finalizar`. A saída final é um JSON `{"resumo": ..., "sucesso": true}`.

## 8. Testar o portão de ZIP com um projeto real

```bash
python3 importador_zip/inspecionar_zip.py /caminho/de/algum_projeto.zip
```

Se `pode_auto_prosseguir` vier `true`, o `diretorio_extraido` do
relatório pode ir direto para o `Orquestrador`. Se vier `false`,
`arquivos_de_risco`/`padroes_suspeitos` no JSON explicam o motivo —
revise antes de prosseguir.

## 9. Abrir a interface desktop

```bash
sudo apt install -y libegl1 libxkbcommon0 libxcb-cursor0
pip install -r requirements.txt
python3 -m interface.janela_principal
```

Escolha a pasta do `~/projeto_teste` (ou outro projeto, ou clique em
"Abrir ZIP…" para importar um projeto compactado — passa pelo mesmo
portão de segurança do passo 8, com um botão de confirmação se o ZIP
tiver itens sinalizados), clique em "Analisar projeto", escreva uma
instrução e clique em "Executar" — mesmo fluxo do passo 7, mas com
painel de progresso ao vivo em vez de esperar o JSON final no
terminal. Ver `interface/README.md` para detalhes.

## 10. Instalar como aplicativo do sistema (comando, ícone, menu)

Em vez de abrir a interface com `python3 -m interface.janela_principal`
toda vez, instale um comando de verdade, com ícone e entrada no menu
de aplicativos:

```bash
pip install -r requirements.txt
sudo ./empacotamento/instalar.sh
```

Isso cria `/usr/local/bin/fabrica-local-ia` (aponta para esta mesma
cópia do repositório — um `git pull` depois não exige reinstalar),
o ícone em `/usr/share/icons/hicolor/scalable/apps/` e a entrada
`.desktop` em `/usr/share/applications/`. Depois, procure
"Fábrica Local de IA" no menu de aplicativos do seu ambiente
desktop, ou rode `fabrica-local-ia` no terminal.

Para desinstalar:

```bash
sudo ./empacotamento/desinstalar.sh
```

## 11. Interpretar um mockup com um modelo de visão

`visao_mockup/interpretar_mockup.py` é um agente reduzido: não fica
ligado junto com o modelo de código (não cabem os dois ao mesmo tempo
em 8GB de VRAM). Ele sobe um `llama-server` só com o modelo de visão,
manda uma imagem, recebe a descrição dos elementos, e desliga o
servidor sozinho.

**Validado nesta sessão** contra Qwen2.5-VL-7B-Instruct numa RX 580 via
Vulkan: a descrição bateu com precisão contra um mockup real (botões,
cards, árvore de arquivos, menu — tudo lido corretamente).

**Sobre o modelo**: apesar de LLaVA ser o nome mais conhecido, ele hoje
é considerado legado no llama.cpp (exige scripts de conversão manual —
ver `tools/mtmd/legacy-models`). A lista atual de modelos
pré-quantizados prontos para `-hf` está em
`~/llama.cpp/docs/multimodal.md` — Qwen2.5-VL-7B-Instruct-GGUF é o que
validamos, mas Gemma 3, SmolVLM e InternVL também estão na lista se
quiser comparar.

### Alternativa leve: MiniCPM-V-4.6

`Qwen2.5-VL-7B` é o motivo de precisar desligar o servidor de código
antes de "Descrever mockup…" — os dois não cabem juntos em 8GB de
VRAM. `MiniCPM-V-4.6` (OpenBMB, ~1,3B — SigLIP2-400M + base
Qwen3.5-0,8B) é bem mais leve (~2GB em GGUF), o que abre a
possibilidade real de rodar visão e código ao mesmo tempo — ainda não
validado nesta máquina, então trate a precisão da descrição como algo
a confirmar antes de confiar nela como o Qwen2.5-VL-7B já validado:

```bash
nohup ./build/bin/llama-server -hf openbmb/MiniCPM-V-4.6-gguf --port 8082 -ngl 20 --ctx-size 4096 > /tmp/llama-vision.log 2>&1 &
```

Pré-requisito: o `llama.cpp` precisa ter sido compilado com suporte a
HTTPS para o `-hf` baixar modelos do Hugging Face — se aparecer
`HTTPS is not supported` no log, falta `libssl-dev`:

```bash
sudo apt install -y libssl-dev
cd ~/llama.cpp
rm -rf build
cmake -B build -DGGML_VULKAN=ON
cmake --build build --config Release -j$(nproc)
```

**Suba o servidor de visão em segundo plano** (se rodar em primeiro
plano na mesma aba, ele morre assim que você digitar o próximo
comando):

```bash
cd ~/llama.cpp
nohup ./build/bin/llama-server -hf ggml-org/Qwen2.5-VL-7B-Instruct-GGUF --port 8082 -ngl 20 --ctx-size 4096 > /tmp/llama-vision.log 2>&1 &
sleep 3
curl -s http://127.0.0.1:8082/v1/models   # confirma que subiu antes de seguir
```

**Gere a descrição do mockup** e salve num arquivo (a CLI do módulo já
imprime pronto para redirecionar):

```bash
cd ~/Aldeir
python3 -m visao_mockup.interpretar_mockup \
  --binario ~/llama.cpp/build/bin/llama-server \
  --modelo dummy --mmproj dummy \
  --imagem ~/mockups/tela_principal.png > /tmp/descricao_mockup.txt
```

> Nota: como o servidor já está de pé manualmente (passo acima), é mais
> simples chamar a função Python direto em vez da CLI completa (que
> sobe/derruba seu próprio servidor). Veja o exemplo com
> `interpretar_imagem` na seção de arquitetura, ou rode:
> ```bash
> python3 -c "
> from pathlib import Path
> from visao_mockup.interpretar_mockup import interpretar_imagem
> print(interpretar_imagem('http://127.0.0.1:8082/v1', Path('~/mockups/tela_principal.png').expanduser(), timeout=180))
> " > /tmp/descricao_mockup.txt
> ```

**Desligue o servidor de visão** e suba o de código (os dois não cabem
juntos):

```bash
pkill -f llama-server
./build/bin/llama-server -m ~/modelos/SEU_MODELO_DE_CODIGO.gguf --port 8080 --jinja -ngl 20 --ctx-size 4096
```

**Rode o orquestrador com a descrição do mockup como contexto** — a
flag `--contexto-arquivo` soma com `--diagnostico` se os dois forem
passados juntos:

```bash
cd ~/Aldeir
python3 -m orquestrador.orquestrador --contexto-arquivo /tmp/descricao_mockup.txt \
  /caminho/do/projeto "implemente a tela desse mockup"
```

A interpretação do mockup é sempre um passo separado, antes de ligar
o modelo de código — não uma ferramenta que o agente chama no meio do
raciocínio (o orquestrador não gerencia troca de servidor sozinho, e
os dois modelos não cabem juntos na VRAM).

Se o servidor não ficar pronto a tempo, `ServidorVisaoIndisponivelError`
mostra o final do stderr do `llama-server` — normalmente falta de
`--mmproj` suportado por essa build, ou VRAM insuficiente por já ter
outro modelo carregado (confira `nvidia-smi`/`radeontop` e desligue o
modelo de código antes de testar este).

## 12. Delegar sub-tarefas a um microagente

`microagentes/delegar_tarefa.py` sobe um modelo pequeno (0,3B–1B) sob
demanda pra resolver sub-tarefas isoladas (gerar uma função pequena,
resumir um trecho, explicar um erro) sem envolver o modelo principal.

Diferente de `busca_codigo`/`visao_mockup`, o servidor do coordenador
**continua rodando** enquanto este sobe o dele — coordenador (~3-7B) +
microagente (0,3-1B) juntos ficam bem abaixo de 8GB de VRAM, então
cabem os dois ao mesmo tempo (diferente de código+visão, ambos ~7B,
que não cabem juntos). Por isso o padrão aqui é **CPU-only**
(`-ngl 0`) — rodar os dois na GPU ao mesmo tempo soma carga
concorrente, e o incidente que motivou a checagem de temperatura
aconteceu com um único modelo na GPU. Valide primeiro em CPU; só suba
o microagente pra GPU depois de confirmar que o hardware está estável
sob carga de um único modelo (o coordenador) de novo:

```bash
python3 -m microagentes.delegar_tarefa \
  --binario ./llama.cpp/build/bin/llama-server \
  --modelo ~/modelos/qwen2.5-coder-0.5b-instruct.gguf \
  --instrucao "escreva uma função que valida um CPF"
```

**Modelo recomendado**: `Qwen2.5-Coder-0.5B-Instruct` (Apache-2.0,
GGUF oficial) — mesma família do `Qwen2.5-Coder-3B/7B` já usados no
projeto. Roda em CPU por padrão (`--ngl` omitido = 0):

```bash
./llama.cpp/build/bin/llama-server \
  -hf Qwen/Qwen2.5-Coder-0.5B-Instruct-GGUF \
  --port 8083 --host 127.0.0.1 --jinja --ctx-size 4096
```

### Achados testando cinco candidatos numa RX 580 real (Xeon sem AVX2)

Testados de verdade, mesma instrução ("escreva uma função Python que
valida um CPF") em todos, em CPU (`-ngl 0`, padrão):

- **`Qwen2.5-Coder-0.5B-Instruct`** (`Qwen/Qwen2.5-Coder-0.5B-Instruct-GGUF`,
  Apache-2.0) — respondeu rápido, direto, código no formato certo
  (a lógica de CPF em si ficou simplificada, esperado pro tamanho).
  **Confirmado como recomendação padrão.**
- **`ERNIE-4.5-0.3B-PT`** (`unsloth/ERNIE-4.5-0.3B-PT-GGUF`, Apache-2.0) —
  respondeu rápido, mas degenerado: alucinou termos sem sentido,
  misturou espanhol/português, e vazou um caractere chinês no meio do
  texto. Suporte a português fraco nesse checkpoint — **não
  recomendado** pra este projeto (instruções em PT-BR).
- **`MiniCPM5-1B`** (`openbmb/MiniCPM5-1B-GGUF`, Apache-2.0) — é um
  **modelo de raciocínio** (thinking model): gasta tokens num campo
  separado (`reasoning_content`) antes de escrever a resposta final em
  `content`. Com `max_tokens=300` (padrão de teste manual) o raciocínio
  sozinho já estourou o limite e `content` veio vazio — precisou de
  `--max-tokens 2000` pra finalmente responder, e mesmo assim a
  resposta final ficou desconectada do raciocínio (identificou o
  algoritmo certo — módulo 11 — mas implementou algo errado). **Não
  recomendado** pro papel de microagente: o ponto é ser rápido/barato,
  e um modelo de raciocínio é o oposto disso. Mas essa mesma
  característica (raciocinar antes de responder) é exatamente o que se
  quer pra *diagnosticar* um erro — ver seção 13, `analisar_erro`.
- **`Qwen3-0.6B`** (`Qwen/Qwen3-0.6B-GGUF`, Apache-2.0) — formato
  limpo, sem preâmbulo (melhor que o Qwen2.5-Coder nesse quesito
  específico), mas com **bug lógico real**: `first_digit = int(cpf[0])`
  seguido de `if first_digit < 10` — um dígito único é sempre `< 10`,
  então a condição é sempre verdadeira e a função sempre devolve
  `False`, pra qualquer entrada. Código com aparência boa, quebrado por
  completo. **Não recomendado.**
- **`Falcon-H1-0.5B-Instruct`** (`tiiuae/Falcon-H1-0.5B-Instruct-GGUF`,
  licença Falcon) — carregou sem erro de arquitetura (o suporte
  híbrido Transformer+Mamba2 já está mesclado na `llama.cpp` mainline
  usada aqui, boa notícia à parte). Mas foi o pior em qualidade:
  português quebrado (misturou espanhol), errou o que CPF significa
  ("Countrywide Postal Code" — mesmo tipo de erro de domínio do
  MiniCPM5-1B), recusou a tarefa sem motivo real ("não pode/recomenda"
  validar CPF) e documentou a função com 9 dígitos (errado, CPF tem
  11). **Não recomendado.**

**Nenhum dos quatro challengers superou o `Qwen2.5-Coder-0.5B-Instruct`
— confirmado como escolha final** pro papel de microagente nesta
máquina, sem necessidade de testar mais candidatos pra esse papel.

Esse teste revelou uma lacuna real: quando um modelo de raciocínio
estoura `max_tokens` antes de escrever `content`, a resposta vinha
`""` em silêncio — sem distinguir "resposta vazia de propósito" de
"geração cortada no meio". `gerar_resposta` agora levanta
`RespostaTruncadaError` nesse caso especificamente (`content` vazio +
`finish_reason == "length"`), que vira `"erro: ..."` no resultado da
ferramenta pro coordenador, em vez de silêncio.

**Filtro arquitetural importante** (vale pra qualquer candidato novo,
não só os três testados): nem todo modelo pequeno "GGUF existe" serve
aqui. Modelos T5 (encoder-decoder, ex.: FRED-T5, Occiglot5) não têm
chat template/tool-calling no `llama-server` mesmo convertidos pra
GGUF — servem pra tradução/geração de texto solto, não pra seguir uma
instrução delegada. Modelos base sem fine-tune de chat (ex.: Mamba
130M) têm o mesmo problema — sem instruct tuning, não seguem
`PROMPT_SISTEMA_PADRAO`. E, como visto acima, um modelo de
**raciocínio** tecnicamente funciona mas é a escolha errada pro papel
(lento, caro em tokens). Confirme "Instruct"/"Chat" no nome do
checkpoint, chat template documentado, e que **não** é um modelo de
raciocínio antes de adotar um candidato novo pra esse papel.

Na interface, "Configurar microagente…" aponta o binário e o modelo —
opcional, sem isso a ferramenta `delegar_tarefa` simplesmente não
aparece pro agente principal.

## 13. Analisar erros com um modelo de raciocínio

`microagentes/analisar_erro.py` é o par oposto de `delegar_tarefa`:
existe porque o `MiniCPM5-1B` testado acima, ruim pra gerar código
rápido, é candidato natural pra **diagnosticar** um erro — raciocinar
em várias etapas antes de concluir é vantagem aqui, não defeito. Lê
`reasoning_content` (quando o servidor expõe esse campo, além de
`content`) e usa `max_tokens=2000` por padrão, já calibrado pelo teste
real acima (foi o valor que fez o MiniCPM5-1B terminar de responder).

```bash
python3 -m microagentes.analisar_erro \
  --binario ./llama.cpp/build/bin/llama-server \
  --modelo ~/modelos/minicpm5-1b/MiniCPM5-1B-Q4_K_M.gguf \
  --erro "pytest: AssertionError em test_soma: esperado 5, recebido 4"
```

Assim como `delegar_tarefa`, roda em CPU por padrão (`-ngl 0`) — o
coordenador continua na GPU em paralelo — e recusa subir na GPU se
`n_gpu_layers>0` for passado com a placa quente (mesma checagem de
temperatura via sysfs).

Na interface, "Configurar analisador de erros…" aponta o binário e o
modelo — opcional e independente de "Configurar microagente…", sem
isso a ferramenta `analisar_erro` simplesmente não aparece pro agente
principal. Os dois botões podem estar configurados ao mesmo tempo,
cada um com um modelo diferente pro seu papel.

## Achados testando contra um modelo real (Xeon + RX 580, Qwen2.5-Coder-7B)

Estes já foram encontrados e corrigidos nesta sessão — deixados aqui
para quem seguir o guia não precisar redescobrir. O achado principal
(#2) só ficou claro depois de descartar duas hipóteses erradas (#2a,
#2b) — registradas aqui porque a investigação em si é útil:

1. **`llama-server` precisa de `--jinja`** para ativar o
   processamento de chat template necessário para tool calling. Sem
   isso, o modelo escreve texto comum em vez de uma chamada
   estruturada.
2. **O `llama-server` (nesta versão) não aplica de verdade a gramática
   de `tool_calls` para o Qwen2.5-Coder, mesmo com `--jinja` e
   `tool_choice: "required"`.** O modelo devolve tudo como texto livre
   em `message.content` — inclusive narrando um plano inteiro de
   várias etapas em markdown com blocos ` ```json ` embutidos, em vez
   de parar numa única chamada. Confirmado testando com dois quants
   diferentes (Q4_K_M e Q6_K, bem menos agressivo) — o comportamento
   foi o mesmo nos dois, descartando quantização como causa.
   - *Hipótese descartada (#2a):* achávamos que era geração
     descontrolada por quantização agressiva (Q4_K_M). Trocar para
     Q6_K não mudou nada — mesmo problema.
   - *Hipótese descartada (#2b):* achávamos que `tool_choice: "required"`
     resolvia (é o que a documentação do llama.cpp recomenda para esse
     caso). Não resolveu — o parâmetro parece ser ignorado por esse
     modelo/versão.
   - **Correção real**: `orquestrador/orquestrador.py:extrair_chamada_de_texto`
     varre `message.content` e extrai o primeiro objeto JSON válido no
     formato `{"name": ..., "arguments": {...}}`, mesmo dentro de
     blocos markdown ou com texto ao redor. O orquestrador usa essa
     extração como fallback sempre que o servidor não devolve
     `tool_calls` estruturado — funciona independente do motor/modelo
     respeitar ou não o tool calling nativo do OpenAI. Já está no
     código, nada a fazer aqui.
3. **`max_tokens` (padrão 512) limita o tamanho da resposta** — uma
   chamada de ferramenta válida tem poucas dezenas de tokens, então
   isso corta cedo qualquer geração longa demais. Se mesmo assim não
   der para extrair uma chamada válida do que foi gerado até o corte,
   levanta `GeracaoTruncadaError` com uma amostra do conteúdo (em vez
   de um erro genérico ou um `JSONDecodeError` confuso).
4. **Timeout**: processar o prompt inicial (system prompt + 4
   ferramentas + diagnóstico) pode passar de 120s em CPU sem AVX2 +
   GPU híbrida. O padrão agora é 300s; se ainda assim der timeout, use
   `--timeout-llm 600` (ou mais) na CLI do orquestrador.

## O que observar e reportar de volta

Se algo além do já corrigido aparecer:

1. **Formato de `tool_calls`** diferente do padrão OpenAI
   (`choices[0].message.tool_calls`) ainda dá erro de
   `KeyError`/`json.JSONDecodeError` — me avise com a resposta bruta
   do servidor para eu ajustar o parsing.
2. **Qualidade das decisões do modelo** — o `PROMPT_SISTEMA` é
   propositalmente simples; se o modelo ficar em loop, chamar
   ferramentas erradas, ou não finalizar, isso é ajuste de prompt, não
   bug de infraestrutura.
