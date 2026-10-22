# Validação da Fase 2 — MGPUSim

Data: 2026-10-22 · ambiente: VM de nuvem Linux (sem GPU), executada como root, com `unshare -n` disponível.

## Critérios de conclusão (ROADMAP)
| Critério | Estado |
|---|---|
| Build isolado em `data/` | **sim** — `data/_sim/mgpusim` (fonte, GOPATH, cache, binário); Go 1.27.0 baixado para dentro desse cache (o Go do sistema, 1.24.7, não foi tocado). Binário `sha256 e0d1c97a…c9f4f`, idêntico entre duas compilações (`-trimpath`) |
| Execução de exemplo mínimo com timeout | **sim** — amostra `fir`, `-timing -verify`, ~0,7–0,9 s, rede isolada, ambiente limpo; o próprio simulador reportou `Passed!` |
| Resultados com `origin=simulated` | **sim** — 18 resultados no banco (3 execuções válidas × 6 métricas), ligados ao experimento `SIM-MGPUSIM-FIR` (nível B, teste de infraestrutura) |
| Documento do que o modelo cobre/não cobre | **sim** — `docs/FASE2_MGPUSIM.md` |

## Resultado simulado (modelo GCN3 / R9 Nano; NÃO é a RX 580)
`fir -length 1024 -taps 16`: `kernel_time` = **7,747 µs simulados**, 4 CUs ativas (de 64), 6272 instruções de CU, CPI médio de CU 4,94 e de SIMD 7,72.
**Idêntico nas 3 execuções** (determinismo observado, não garantia geral; `-parallel` não é usado).

## Testes
`./scripts/validar.sh`: gofmt, vet, build e **81 testes, 0 falhas**. Novos, em `internal/simulation`:
catálogo (commit de 40 hex, `-disable-rtm` obrigatório, flags proibidas), argumentos validados e limitados, extração de `tar`
(traversal recusado, symlinks ignorados), `Prepare` com repositório Git local, `ParseDeps`, **portões de aprovação** (sem revisão /
sem aprovação / commit errado / sem build / `go.sum` alterado), execução com binário falso (ambiente limpo, argumentos exatos,
resultados `simulated`, experimento que impede alegar melhoria), **timeout**, **binário adulterado**, limites de execução e extração de métricas.

## Defeitos achados na execução real e corrigidos
1. **Métricas não extraídas** nas 3 primeiras execuções: valores infinitos viram `NULL` no driver SQLite (CPI de CU ociosa). Agora `NULL/Inf/NaN` são ignorados (nunca zerados). Essas 3 execuções permanecem no banco (#1–#3) com a nota do erro; as válidas são #4–#6.
2. **Reprodutibilidade falsa:** o laboratório imprimiu "kernel_time idêntico: true" comparando 0 com 0 (sem métricas). Corrigido com `Deterministic()`, que exige `kernel_time` presente e igual; coberto por teste de regressão.
3. Estrutura: o cache de módulos dentro de `data/` quebrava `go build ./...`; o workspace foi movido para `data/_sim` (pastas iniciadas por `_` são ignoradas pelo Go).

## Aprovação do código de terceiros — transparência
A etapa `aprovar` é um portão humano. Nesta sessão ela foi registrada como **"sessão Claude Code (autorização do usuário: 'avançar para fase 2')"**,
com base no pedido do usuário de avançar a fase (cujo roadmap inclui compilar e executar o MGPUSim). **Não é uma aprovação nominal do usuário.**
Na sua máquina, rode `scripts/fase2-mgpusim.sh`, leia a revisão e aprove com o seu nome.

## Limites e o que não foi validado
- Nenhum teste fora desta VM (nem Windows, nem a máquina da RX 580). O coletor/CLI de simulação é **Linux**.
- Revisão de código **por padrões e leitura parcial** (não é auditoria); o binário executa tudo que o simulador contém.
- Sandbox sem limite de memória/CPU (só timeout); isolamento de rede depende de `unshare`.
- Só a amostra `fir`; sem comparação com medições reais (Fase 5). **Nenhuma relação entre 7,747 µs simulados e a RX 580 foi estabelecida.**
- A RX 580 2048SP não foi modelada (parâmetros do modelo são os da R9 Nano).
- Fase 3 **não** foi iniciada.
