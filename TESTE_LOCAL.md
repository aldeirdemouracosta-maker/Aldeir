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
sudo apt install -y bubblewrap mesa-vulkan-drivers vulkan-tools build-essential cmake git python3
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
  --host 127.0.0.1
```

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

## O que observar e reportar de volta

Como o loop do orquestrador nunca foi testado contra um modelo real
(só contra um mock nesta sessão de desenvolvimento), vale prestar
atenção a três coisas específicas na primeira rodada:

1. **Formato de `tool_calls` na resposta do llama-server** — o
   parsing em `orquestrador/orquestrador.py:chamar_llm` espera o
   formato padrão OpenAI (`choices[0].message.tool_calls`). Se o
   llama-server devolver algo ligeiramente diferente, isso vai
   aparecer como erro de `KeyError`/`json.JSONDecodeError` — me avise
   com a resposta bruta do servidor para eu ajustar o parsing.
2. **Qualidade das decisões do modelo** — o `PROMPT_SISTEMA` é
   propositalmente simples; se o modelo ficar em loop, chamar
   ferramentas erradas, ou não finalizar, isso é ajuste de prompt, não
   bug de infraestrutura.
3. **Tempo de resposta** — se `chamar_llm` der timeout (padrão de 120s
   no HTTP, mais o `timeout_segundos` do sandbox por comando), pode
   ser preciso aumentar os timeouts para modelos maiores rodando em
   CPU+GPU híbrido.
