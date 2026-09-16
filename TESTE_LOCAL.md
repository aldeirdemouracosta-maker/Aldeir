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
  --jinja
```

`--jinja` é obrigatório — ativa o processamento de chat template
necessário para o tool calling do orquestrador funcionar (sem isso o
modelo escreve texto comum em vez de uma chamada estruturada).

Deixe rodando num terminal separado.

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

## Achados testando contra um modelo real (Xeon + RX 580, Qwen2.5-Coder-7B)

Estes já foram encontrados e corrigidos nesta sessão — deixados aqui
para quem seguir o guia não precisar redescobrir:

1. **`llama-server` precisa de `--jinja`** para ativar o
   processamento de chat template necessário para tool calling. Sem
   isso, o modelo escreve texto comum em vez de uma chamada
   estruturada.
2. **Mesmo com `--jinja`, o Qwen2.5-Coder escreve a chamada de
   ferramenta como JSON solto** em vez de embrulhada em `<tool_call>`
   — formato que o parser do `llama-server` não reconhece, então a
   chamada nunca chega como `tool_calls` estruturado. Corrigido
   mandando `tool_choice: "required"` na requisição
   (`orquestrador/orquestrador.py:chamar_llm`), que força o
   `llama-server` a usar a gramática que garante o formato certo. Já
   está no código — nada a fazer aqui.
3. **Geração descontrolada com `tool_choice=required`**: mesmo com o
   formato certo, em Q4_K_M o modelo pode ultrapassar 1000+ tokens
   tentando gerar uma chamada que deveria ter ~15 (confirmado nos
   logs do `llama-server`: geração ativa e contínua a ~21 tok/s, não
   travamento — só sem parar). Isso parecia timeout, mas era geração
   sem fim. Corrigido com `max_tokens` (padrão 512) na requisição:
   corta cedo e levanta `GeracaoTruncadaError` em vez de deixar o
   cliente esperar minutos por algo que não ia terminar direito. Se
   isso continuar acontecendo com frequência, o próximo passo é trocar
   de quantização (Q5_K_XL/Q6_K_XL em vez de Q4_K_M) — geração de
   tool call é sensível a quantização agressiva.
4. **Timeout**: processar o prompt inicial (system prompt + 4
   ferramentas + diagnóstico) mais a geração com `tool_choice=required`
   pode passar de 120s em CPU sem AVX2 + GPU híbrida. O padrão agora é
   300s; se ainda assim der timeout (e não `GeracaoTruncadaError`), use
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
