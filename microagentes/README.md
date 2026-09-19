# Microagentes — delegação de sub-tarefas pequenas

`delegar_tarefa.py` sobe um `llama-server` temporário com um modelo
**pequeno e rápido** (0,3B–1B, ex.: `Qwen2.5-Coder-0.5B`), manda uma
única instrução (sem tool calling — o microagente não tem acesso a
ferramenta nenhuma, só gera texto/código), devolve a resposta, desliga
o servidor. Mesmo padrão de "agente reduzido" já usado em
`busca_codigo/buscar_codigo.py` e `visao_mockup/interpretar_mockup.py`.

## Por quê

Nem toda sub-tarefa dentro de uma execução do orquestrador precisa do
modelo principal (o "coordenador"): gerar uma função pequena e
isolada, resumir um trecho, explicar uma mensagem de erro. Um modelo
de 0,3B–1B resolve isso mais rápido — e mais leve em VRAM/CPU — do que
rodar tudo no coordenador, que fica livre pra decidir o que fazer com
o resultado (ex.: escrever num arquivo, seguir pra próxima etapa).

Diferente de `busca_codigo`/`visao_mockup` (que assumem que só um
modelo por vez cabe na GPU, como código e visão — ambos ~7B — não
cabem juntos em 8GB), o servidor do coordenador **continua rodando**
enquanto `delegar_tarefa` sobe o seu: um coordenador (~3-7B) e um
microagente (0,3-1B) juntos ficam bem abaixo dos 8GB de VRAM, folga
suficiente pra rodar os dois ao mesmo tempo. `delegar_tarefa` não
desliga nada além do processo que ele mesmo sobe.

**Por isso o padrão é CPU-only** (`n_gpu_layers=0`), diferente dos
outros agentes reduzidos: rodar dois modelos na GPU ao mesmo tempo
soma carga concorrente, não sequencial — e o incidente real que
motivou a checagem de temperatura (ver `TESTE_LOCAL.md`) já aconteceu
com um único modelo. Um modelo de 0,3-1B roda bem em CPU sem ficar
impraticável; suba pra GPU (`n_gpu_layers>0`) só depois de confirmar
que o hardware está estável sob carga de um único modelo primeiro.

## Ferramenta no orquestrador

`delegar_tarefa(instrucao, contexto)` é **opcional**, igual
`buscar_codigo`: só entra na lista de ferramentas anunciada ao modelo
(`montar_ferramentas`) se `caminho_binario_microagente`/
`caminho_modelo_microagente` forem passados ao `Orquestrador` — sem
isso configurado, a ferramenta simplesmente não existe pro modelo.

O microagente **não recebe** o histórico da conversa nem acesso a
`ler_arquivo`/`escrever_arquivo`/`executar_comando` — só a instrução e
um `contexto` opcional que o coordenador decide passar. Isso é
deliberado: mantém o microagente simples e previsível (uma chamada,
uma resposta), sem o risco de um modelo pequeno tentando rodar um loop
de agente completo e se perdendo.

## Segurança de GPU

`n_gpu_layers=0` (CPU) por padrão, `ctx_size=4096`. Se `n_gpu_layers>0`
for passado explicitamente, confere a temperatura da GPU
(`motor_ia.temperatura_gpu_celsius`) antes de subir o servidor,
recusando se estiver acima do limite seguro — mesma lógica de
`buscar_codigo`/`interpretar_mockup`, ver `motor_ia/README.md` e
`TESTE_LOCAL.md` para o incidente real que motivou isso.

## Escolha do modelo

`Qwen2.5-Coder-0.5B-Instruct` (Apache-2.0, GGUF oficial) é a
recomendação inicial — mesma família do `Qwen2.5-Coder-3B/7B` já
usados no projeto, reduzindo o risco de tool-calling/chat-template
"surpresa" (aqui nem é usado tool calling, mas o chat template
continua relevante pra qualidade da resposta). Ver `TESTE_LOCAL.md`
para outros candidatos avaliados (ERNIE-4.5-0.3B, MiniCPM5-1B) e por
que modelos T5/encoder-decoder ou state-space puro (Mamba base) não
servem aqui — sem chat template/instruct tuning, não seguem a
instrução delegada.

## Uso

Como biblioteca:

```python
from microagentes.delegar_tarefa import delegar_tarefa

resposta = delegar_tarefa(
    Path("./llama.cpp/build/bin/llama-server"),
    Path("~/modelos/qwen2.5-coder-0.5b-instruct.gguf").expanduser(),
    "escreva uma função que valida um CPF",
)
```

CLI:

```bash
python3 -m microagentes.delegar_tarefa \
    --binario ./llama.cpp/build/bin/llama-server \
    --modelo ~/modelos/qwen2.5-coder-0.5b-instruct.gguf \
    --instrucao "escreva uma função que valida um CPF"
```

Na interface, o botão **"Configurar microagente…"** aponta o
`llama-server` e o GGUF do microagente (mesmo padrão do "Configurar
busca semântica…" — sempre pede os dois de novo, não reaproveita
caminho salvo). Opcional: sem configurar, "Executar" funciona
normalmente, só sem a ferramenta `delegar_tarefa` disponível pro
agente.
