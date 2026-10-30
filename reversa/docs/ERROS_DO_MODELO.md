# O que os modelos erraram e como o programa corrige

Observado rodando `reversa ps1` com `qwen2.5-coder:7b` (Ollama, GPU) em `testdata/exemplo2.exe`.
Regra aprendida: tudo que o programa consegue calcular com certeza deve ir pronto para o relatório e para o
prompt. O modelo só interpreta; nunca deve copiar números nem decidir lógica de laço.

| Erro do modelo | Causa | Correção no programa |
|---|---|---|
| Escreveu `0x4256` onde o certo era `0x10a0` | A desmontagem mostrava deslocamentos em decimal (`4256`) | Hexadecimal em toda a desmontagem; endereço do registrador no comentário |
| Citações `[E#]` trocadas entre funções | O modelo escrevia os números de evidência | Citações geradas pelo programa; o modelo escreve só o resumo geral |
| Inverteu a lógica de `wait_vblank` | O fato dizia só "sai quando a leitura muda" | Condição exata derivada: `repete enquanto (I_STAT & 0x1) == 0; sai quando (I_STAT & 0x1) != 0` |
| "O laço infinito começa em 0x80010050" | Faltava o corpo do laço | Chamadas dentro do laço listadas; entrada rotulada |
| Errou a conta de `0x03000001` ("adiciona 1") | Valores escritos não eram informados | Valores constantes escritos em cada registrador, ou "valor variável" |

### Primeiro jogo real (Valkyrie Profile, tradução pt-BR, executável de 128 KB, 313 funções)
| Problema | Correção |
|---|---|
| "chama recursivamente" para funções que chamam **outras** funções | Recursão só vale se a função chama o próprio endereço (`Recursão (derivado)`); prompt proíbe o termo sem o fato |
| Listou todos os registradores do MIPS como "informação" | Prompt proíbe listar registradores e instruções; respostas limitadas a 200 tokens (`-worker-tokens`) |
| Gastou o modelo (30 s cada) em stubs minúsculos de BIOS e chutou "chamada de sistema" / "aloca memória" | Stub de BIOS reconhecido pelo padrão `$t2=0xA0/B0/C0; jr $t2; $t1=N`; relatório diz `BIOS A(0x33)` e o modelo não é consultado |
| Strings referenciadas passavam despercebidas | `Strings referenciadas (derivado)` a partir de `lui`+`addiu`/`ori` que apontam para texto ASCII |

### Defeito do próprio programa achado no processo
A propagação de constantes limpava os registradores no `jal`, **antes** do delay slot. No MIPS o delay slot executa
antes da chamada, então `jal f; addiu $a0,$a0,k` usa o `$a0` de antes do `jal`. Corrigido (efeito da chamada só depois
do delay slot) com teste de regressão.

### Comparação 7B x 14B no mesmo jogo (4 funções)
O 14B levou 5 min 55 s contra ~26 s por função do 7B (≈3,5x), com qualidade parecida, e também escreveu "chamadas
recursivas" para chamadas a **outra** função (o verificador descartou). O limite é a informação disponível para cada
função (isolada, sem nomes), não o tamanho do modelo.

Resultado da execução com `exemplo2`: `wait_vblank` descrito corretamente (espera o bit ser ativado, depois escreve 0),
`gpu_reset`, `dma_to_gpu`, `cd_command`, `read_timer`, `checksum` e `dispatch` coerentes com o código,
8 funções em 43 s no total (a maior parte vinda do cache).

## Limites que continuam
- O resumo geral ainda é genérico ("inicializador do sistema"): o modelo não tem o contexto de um jogo real.
- A derivação de condição só cobre leitura de hardware + `andi` + `beq`/`bne` contra `$zero`.
  Outros padrões (`slt`, `bltz`) saem como "condição de saída não determinada".
- Só foram testados programas pequenos escritos para este projeto. Nenhum disco real passou pelo pipeline.
- A tabela de nomes de registradores veio da memória da documentação psx-spx e foi conferida só nos
  endereços usados pelos exemplos.

## Lacunas do programa vistas em código real (função de comando do CD-ROM, `CD_cw`)
| Lacuna | Correção |
|---|---|
| Nenhum fato de hardware: a função escreve nos registradores do CD-ROM por **ponteiros guardados em variáveis globais** | Procura no executável globais que sempre recebem o mesmo endereço de hardware e resolve o `lw`; o relatório mostra `[via ponteiro global 0x...]`. Globais com valores diferentes ou desconhecidos são ignoradas |
| Strings de formato (`"CD_cw: %s\n"`) rejeitadas por terem `\n` e símbolos | Aceita `\n`, `\r`, `\t` e exige só 1/3 de letras |
| Função truncada em 256 instruções sem aviso | Aviso explícito no relatório e no `func` quando a função continua além do limite |

Limitação: a resolução de globais é linear e assume que só as escritas constantes do próprio executável mudam
a variável; ponteiros que aliasam a global, ou inicialização feita fora do executável (overlays), não são vistos.
