# Microagentes — delegação de sub-tarefas pequenas

Dois módulos irmãos, mesmo padrão de "agente reduzido" já usado em
`busca_codigo/buscar_codigo.py` e `visao_mockup/interpretar_mockup.py`
(sobe um `llama-server` temporário, faz uma chamada, desliga), mas com
papéis opostos de propósito:

- **`delegar_tarefa.py`** — modelo **pequeno e rápido** (0,3B–1B, ex.:
  `Qwen2.5-Coder-0.5B`) pra sub-tarefas simples e autocontidas. Sem
  tool calling, sem histórico da conversa.
- **`analisar_erro.py`** — modelo **de raciocínio** (ex.: `MiniCPM5-1B`)
  pra diagnosticar a causa de um erro antes de tentar corrigi-lo. Mais
  lento de propósito — aqui precisão importa mais que velocidade.

A separação existe porque testamos os dois papéis com o mesmo tipo de
modelo e não funcionou: um modelo de raciocínio é ruim gerando código
rápido (gasta tokens demais "pensando"), e um modelo rápido não pensa
o suficiente pra diagnosticar um erro direito. Ver TESTE_LOCAL.md,
seção 12, pros achados reais que levaram a essa divisão.

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
recomendação — **testado numa RX 580 real** (ver `TESTE_LOCAL.md`,
seção 12): respondeu rápido e no formato certo. Mesma família do
`Qwen2.5-Coder-3B/7B` já usados no projeto, reduzindo o risco de
chat-template "surpresa".

Cinco outros candidatos testados na mesma sessão, todos
**descartados** com motivo concreto: `ERNIE-4.5-0.3B` (suporte a
português fraco — alucinou, misturou idiomas, vazou caractere chinês),
`MiniCPM5-1B` (é um **modelo de raciocínio** — gasta o orçamento de
tokens "pensando" num campo separado antes de responder, lento e caro
pro papel de microagente; ver `RespostaTruncadaError` abaixo),
`Qwen3-0.6B` (formato de resposta limpo, mas lógica sempre-falsa — bug
real, não estilístico), `Falcon-H1-0.5B-Instruct` (carregou sem
problema — arquitetura híbrida já suportada na `llama.cpp` mainline —
mas português quebrado, erro de domínio sobre o que é CPF, recusa sem
motivo) e `TinySwallow-1.5B-Instruct` (pior resultado dos seis:
alucinou conceitos sem relação com CPF, indexou fora dos limites da
string, nunca terminou a resposta — além de ter licença com restrição
de uso comercial). Ver `TESTE_LOCAL.md` para os detalhes de cada
teste, e por que modelos T5/encoder-decoder ou state-space puro (Mamba
base) nem chegam a rodar aqui — sem chat template/instruct tuning, não
seguem a instrução delegada.

**Evite modelos de raciocínio** ("thinking"/"reasoning" no nome ou na
documentação) pra `delegar_tarefa` — mesmo que tecnicamente funcionem,
o ponto desse papel é ser rápido e barato, e um modelo de raciocínio é
estruturalmente o oposto disso. Isso não significa que um modelo de
raciocínio seja inútil pro projeto — ver `analisar_erro.py` abaixo,
onde a mesma característica que atrapalhou aqui (raciocinar antes de
responder) é exatamente o que se quer.

## Geração truncada sem resposta

`gerar_resposta` levanta `RespostaTruncadaError` quando o modelo
atinge `max_tokens` **sem** produzir nada em `message.content` (mesma
ideia do `GeracaoTruncadaError` do orquestrador, versão local deste
módulo) — achado real testando `MiniCPM5-1B` (modelo de raciocínio):
ele gasta o orçamento de tokens em `reasoning_content`, um campo
separado, e `content` vem `""` se estourar o limite antes de começar a
responder de verdade. Sem essa checagem, `delegar_tarefa` devolveria
uma string vazia em silêncio, e o coordenador não teria como saber que
foi "geração cortada" em vez de "resposta vazia de propósito". No
orquestrador, isso vira `"erro: ..."` no resultado da ferramenta,
igual qualquer outro erro de `delegar_tarefa`.

## `analisar_erro.py` — diagnóstico via modelo de raciocínio

`analisar_erro(erro, contexto)` é ferramenta **opcional** no
orquestrador, mesmo padrão de `delegar_tarefa`/`buscar_codigo`: só
existe pro modelo se `caminho_binario_analise`/`caminho_modelo_analise`
forem configurados. Porta padrão diferente (`8084` vs `8083` do
`delegar_tarefa`) — os dois podem, em tese, rodar na mesma execução
(analisar um erro, depois delegar a correção).

Duas diferenças de propósito em relação a `delegar_tarefa`:

- **Lê `reasoning_content`, não só `content`.** Quando um servidor de
  raciocínio expõe esse campo separado (visto na prática com
  MiniCPM5-1B), `extrair_analise` prefere `content` (resposta final),
  mas cai para `reasoning_content` se `content` vier vazio — aqui o
  raciocínio *é* a análise, não é descartável como em
  `delegar_tarefa.gerar_resposta`.
- **`max_tokens=2000` por padrão** (vs `1024` do `delegar_tarefa`) —
  orçamento maior de propósito, porque um modelo de raciocínio gasta
  tokens "pensando" antes de responder (MiniCPM5-1B precisou de 2000
  pra terminar no teste real, ver TESTE_LOCAL.md).

Mesma infraestrutura de segurança que o resto do projeto:
`n_gpu_layers=0` por padrão (CPU — o coordenador continua na GPU em
paralelo), checagem de temperatura se `n_gpu_layers>0` for passado
explicitamente, `RespostaTruncadaError` (reaproveitado de
`delegar_tarefa.py`) se nem `content` nem `reasoning_content` vierem
com nada.

**Modelo recomendado**: `MiniCPM5-1B` — descartado como microagente de
`delegar_tarefa` justamente por raciocinar antes de responder, mas é
exatamente o que se quer aqui.

## Uso

Como biblioteca:

```python
from microagentes.delegar_tarefa import delegar_tarefa

resposta = delegar_tarefa(
    Path("./llama.cpp/build/bin/llama-server"),
    Path("~/modelos/qwen2.5-coder-0.5b-instruct.gguf").expanduser(),
    "escreva uma função que valida um CPF",
)

from microagentes.analisar_erro import analisar_erro

analise = analisar_erro(
    Path("./llama.cpp/build/bin/llama-server"),
    Path("~/modelos/minicpm5-1b/MiniCPM5-1B-Q4_K_M.gguf").expanduser(),
    "pytest: AssertionError em test_soma: esperado 5, recebido 4",
)
```

CLI:

```bash
python3 -m microagentes.delegar_tarefa \
    --binario ./llama.cpp/build/bin/llama-server \
    --modelo ~/modelos/qwen2.5-coder-0.5b-instruct.gguf \
    --instrucao "escreva uma função que valida um CPF"

python3 -m microagentes.analisar_erro \
    --binario ./llama.cpp/build/bin/llama-server \
    --modelo ~/modelos/minicpm5-1b/MiniCPM5-1B-Q4_K_M.gguf \
    --erro "pytest: AssertionError em test_soma: esperado 5, recebido 4"
```

Na interface, os botões **"Configurar microagente…"** e **"Configurar
analisador de erros…"** apontam o `llama-server` e o GGUF de cada um
(mesmo padrão do "Configurar busca semântica…" — sempre pedem os
caminhos de novo, não reaproveitam o que foi salvo). Os dois são
independentes e opcionais: sem configurar, "Executar" funciona
normalmente, só sem a respectiva ferramenta disponível pro agente.
