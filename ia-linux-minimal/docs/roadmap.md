# Roadmap

| Versão | Nome | Status |
|---|---|---|
| 0.1.0-alpha1 | boot mínimo | especificado (ver `CHANGELOG.md`) |
| 0.1.1-alpha2 | hardware físico (BIOS/UEFI, partições) | especificado |
| 0.2.0-alpha3 | inferência CPU (llama.cpp) | especificado |
| 0.3.0-alpha4 | Vulkan/RADV | especificado |
| 0.4.0-alpha5 | AI Core (Rust) — daemon + IPC | implementado |
| 0.5.0-alpha6 | Multiagente | implementado |
| 0.6.0-alpha7 | AI Memory (DAMON_RECLAIM + cgroup v2) | implementado |
| 0.7.0-alpha8 | AI Scheduler (cgroup v2 cpu.weight — sched_ext adiado) | implementado |
| **0.8.0-alpha9** | **Scheduler adaptativo (telemetria real + regra determinística)** | **implementado nesta árvore** |
| 0.9 | Imagem instalável (ISO/IMG para SSD/pendrive) | planejado |
| 1.0 | Release reproduzível | planejado |

## 0.5 — Multiagente (implementado)

Vários agentes (planejador, programador, pesquisador, crítico, executor
— ver `ai-core/src/agent.rs::PLANNED_ROLES`) compartilham um único
modelo carregado via `llama-server`, em vez de um modelo por agente.
`AgentManager` mantém uma fila de tarefas e um único worker thread que as
processa sequencialmente (não em paralelo — decisão deliberada para
hardware modesto, onde vários agentes disputando o mesmo modelo ao mesmo
tempo só disputariam RAM/CPU sem ganho real). Ver `AGENT` no protocolo
IPC (`ROLES`, `TASK <papel> <texto>`, `STATUS <id>`, `LIST`) e o cliente
`ia-agent`.

Ainda não implementado (candidato a uma etapa futura, não necessariamente
0.6): prioridades entre tarefas (hoje é FIFO puro) e agentes que chamam
outros agentes (ex.: um "crítico" revisando a saída de um "programador"
automaticamente).

## 0.6 — AI Memory (implementado)

Duas peças, ver `ai-core/src/memory.rs`:

1. **DAMON_RECLAIM ajustado por perfil de hardware** — `MEMORY APPLY`
   escreve `enabled`/`min_age`/`quota_ms`/`quota_sz` em
   `/sys/module/damon_reclaim/parameters` (parametrizável via
   `IA_DAMON_SYSFS`) com heurísticas iniciais por perfil (TINY/LOW mais
   agressivos, LARGE mais conservador — não medidas em hardware real).
2. **Proteção via cgroup v2** — a regra "RAM do modelo/KV cache nunca é
   candidata a reclaim agressivo" é implementada com `memory.low` no
   cgroup do processo `llama-server` (PID lido de `/run/ia-server.pid`),
   com piso calculado a partir do tamanho do arquivo `.gguf` ativo. Isso
   foi escolhido em vez dos filtros de memcg do próprio DAMON (que
   existem, mas exigem a hierarquia sysfs completa de
   kdamonds/contexts/schemes — mais complexa e não haveria como validar
   neste ambiente de desenvolvimento, que não tem DAMON nem cgroup v2
   disponíveis).

Não implementado ainda: ajuste *adaptativo* em tempo real com base em
métricas observadas (hoje é só a aplicação de uma heurística estática
por perfil, sob demanda via `MEMORY APPLY`). A 0.8 trouxe telemetria e
uma regra adaptativa para o **scheduler** (`SCHED ADAPT`); a mesma ideia
aplicada à memória (ajustar DAMON_RECLAIM a partir de métricas
observadas, não só do perfil estático) continua em aberto para uma
etapa futura.

## 0.7 — AI Scheduler (implementado, escopo reduzido)

O plano original era um scheduler experimental via `sched_ext` (BPF,
carregado/removido dinamicamente, com fallback automático para o
scheduler padrão do Linux em caso de falha), reaproveitando
conceitualmente o modelo de estados/recompensas do AI-Linux acadêmico
(dissertação de Nathan Loretan, 2018). Ao chegar nesta etapa, o mesmo
ambiente de desenvolvimento que não tem DAMON/cgroup v2 (0.6) também não
tem `bpftool` nem `/sys/kernel/sched_ext` — não havia como compilar,
carregar ou testar um scheduler BPF de verdade. Ver a decisão completa
em `kernel/patches/README.md`.

Entregue em vez disso: `SCHED APPLY` ajusta `cpu.weight` (controlador
`cpu` de cgroup v2) do cgroup do modelo/llama-server por perfil de
hardware — TINY/LOW ganham prioridade maior, LARGE fica mais próximo do
padrão. Mesmo cgroup que `memory.rs` (0.6) já protege com `memory.low` —
ver `ai-core/src/scheduler.rs`. `kernel/config/sched-ext.fragment`
continua preparado (desligado por padrão) para quando um scheduler
`sched_ext` de verdade puder ser desenvolvido contra um kernel real.

## 0.8 — Scheduler adaptativo (implementado)

Métricas de CPU (`/proc/loadavg`), memória (`/proc/meminfo`) e tokens/s
(extraídos da resposta do `llama-server`) alimentando `SCHED ADAPT` —
ver `ai-core/src/telemetry.rs`. Ao contrário de `memory.rs`/
`scheduler.rs`, essas leituras de `/proc` **não** precisam de caminho
parametrizável: existem de verdade neste ambiente de desenvolvimento
(mesmo padrão que `hardware.rs` já usa desde a 0.4), então a telemetria
em si foi validada contra o kernel real deste sandbox, não simulada.

`adapt_weight` é uma regra determinística se-então (throughput caiu +
CPU contendida + memória OK → sobe o peso; throughput bom + CPU ociosa →
volta ao peso base; caso contrário mantém) — **não é aprendizado por
reforço nem qualquer forma de ML**. É exatamente o que a descrição
original desta etapa pedia: "um passo em direção ao aprendizado, não
apenas regras fixas" — telemetria real substituindo o valor estático por
perfil da 0.7, mas ainda não um scheduler que aprende de fato (ajustando
parâmetros a partir de recompensa observada). Isso continua sendo
trabalho futuro, na mesma linha do scheduler `sched_ext` adiado na 0.7.

## 0.9 / 1.0 — Distribuição

Imagem bootável para SSD/pendrive com instalador guiado, modo
`RECOVERY` validado em hardware real (não apenas especificado), e
release reproduzível a partir do código-fonte (`make legal-info` incluído
no processo de release — ver `docs/licenses.md`).
