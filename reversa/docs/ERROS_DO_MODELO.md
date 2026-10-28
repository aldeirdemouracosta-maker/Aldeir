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

Resultado da última execução: `wait_vblank` descrito corretamente (espera o bit ser ativado, depois escreve 0),
`gpu_reset`, `dma_to_gpu`, `cd_command`, `read_timer`, `checksum` e `dispatch` coerentes com o código,
8 funções em 43 s no total (a maior parte vinda do cache).

## Limites que continuam
- O resumo geral ainda é genérico ("inicializador do sistema"): o modelo não tem o contexto de um jogo real.
- A derivação de condição só cobre leitura de hardware + `andi` + `beq`/`bne` contra `$zero`.
  Outros padrões (`slt`, `bltz`) saem como "condição de saída não determinada".
- Só foram testados programas pequenos escritos para este projeto. Nenhum disco real passou pelo pipeline.
- A tabela de nomes de registradores veio da memória da documentação psx-spx e foi conferida só nos
  endereços usados pelos exemplos.
