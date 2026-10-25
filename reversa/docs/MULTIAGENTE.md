# Sugestões para multiagentes locais

O gargalo de um setup local é a GPU, não a CPU. Quase toda otimização abaixo é sobre gastar menos chamadas
de modelo ou usá-las melhor.

## 1. Faça em Go tudo o que não precisa de modelo
Cabeçalho, busca de funções (`jal`), desmontagem, strings e contagem de chamadas são determinísticos,
rápidos e não alucinam. O modelo só entra para **semântica** (o que a função faz). No pipeline `ps1`, o
estágio 1 inteiro roda sem modelo.

## 2. Funil com modelos de tamanhos diferentes
- Operários: modelo pequeno (7B), uma chamada curta por função, sem ferramentas, em paralelo.
- Sintetizador: modelo maior (14B+), uma única chamada com os resumos.
Isso evita gastar o modelo grande em dezenas de trechos pequenos.

## 3. Paralelismo limitado pelo servidor
`orchestrator.Map` limita as chamadas simultâneas. Use `workers` igual a `OLLAMA_NUM_PARALLEL`; acima disso
as requisições só ficam na fila e a latência por chamada piora. Dois modelos diferentes ao mesmo tempo
disputam a VRAM; se não couberem juntos, rode os estágios em sequência (`OLLAMA_MAX_LOADED_MODELS=1`).

## 4. Cache em disco
`llm.Cached` indexa por hash de modelo + mensagens + ferramentas. Reanalisar o mesmo binário, ou retomar após
uma falha, não gasta GPU. Trocar de modelo invalida o cache de propósito.

## 5. Fatos separados de hipóteses
Saída de ferramenta vira evidência com `Limits`. Texto do modelo vira `llm_hipotese`, marcado como não
verificado. O relatório precisa citar `[E#]`. Assim dá para auditar qualquer afirmação.

## 6. Contexto pequeno é o limite real
Corte a entrada (`-insns`), pagine decompilações por função e resuma antes de sintetizar (map-reduce).
Para binários grandes, sintetize em árvore: resumos por módulo, depois um resumo dos resumos.

## 7. Próximas melhorias, por ordem de retorno
1. **Grafo de chamadas:** analisar folhas primeiro e passar o resumo dos chamados para o chamador (contexto
   de baixo para cima). Melhora muito a qualidade dos nomes e resumos.
2. **Verificador:** um segundo agente confere cada hipótese contra a desmontagem (por exemplo, "a função
   escreve em 0x1F801810?") e rebaixa as que não se sustentam.
3. **Constantes do hardware PS1:** mapear endereços de GPU (0x1F801810), SPU, DMA e CD-ROM para nomes antes
   de enviar ao modelo. Reduz alucinação e é determinístico.
4. **Falha isolada:** `Map` já devolve o erro por tarefa; adicionar nova tentativa com recuo e um orçamento
   total de tempo.
5. **Streaming e progresso** na CLI, e saída do relatório em Markdown com a tabela de evidências.
6. **Servidor MCP** em Go para que Claude Code ou outro cliente use as mesmas ferramentas.

## PS1: o que já existe
`internal/ps1`: leitura de PS-X EXE, busca de funções por `jal`, desmontador MIPS R3000 (inclui marcação de
GTE/COP2). Ainda **não** cobre: imagens de disco `.bin/.cue`, executáveis compactados, overlays, jalr/jr
indiretos e tabelas de salto.
