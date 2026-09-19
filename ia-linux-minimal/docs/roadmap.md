# Roadmap

| Versão | Nome | Status |
|---|---|---|
| 0.1.0-alpha1 | boot mínimo | especificado (ver `CHANGELOG.md`) |
| 0.1.1-alpha2 | hardware físico (BIOS/UEFI, partições) | especificado |
| 0.2.0-alpha3 | inferência CPU (llama.cpp) | especificado |
| 0.3.0-alpha4 | Vulkan/RADV | especificado |
| **0.4.0-alpha5** | **AI Core (Rust) — daemon + IPC** | **implementado nesta árvore** |
| 0.5 | Multiagente | planejado |
| 0.6 | AI Memory (DAMON adaptativo) | planejado |
| 0.7 | AI Scheduler (sched_ext + eBPF/Rust) | planejado |
| 0.8 | Scheduler adaptativo (telemetria + aprendizado) | planejado |
| 0.9 | Imagem instalável (ISO/IMG para SSD/pendrive) | planejado |
| 1.0 | Release reproduzível | planejado |

## 0.5 — Multiagente

Vários agentes (planejador, programador, pesquisador, crítico, executor
— ver `ai-core/src/agent.rs::PLANNED_ROLES`) compartilhando um único
modelo carregado via `llama-server`, em vez de um modelo por agente.
`ai-core` ganha um módulo de filas/prioridades; `agent.rs` deixa de ser
placeholder.

## 0.6 — AI Memory

`DAMON`/`DAMON_RECLAIM` (já habilitados em
`kernel/config/ia_linux_x86_64.config`) passam a ser lidos e ajustados
por `ai-core`, com uma regra explícita: RAM do modelo/KV cache/inferência
nunca é candidata a reclaim agressivo; logs/cache/processos
auxiliares/agentes inativos sim.

## 0.7 — AI Scheduler

Scheduler experimental via `sched_ext` (BPF, carregado/removido
dinamicamente, com fallback automático para o scheduler padrão do Linux
em caso de falha — ver `kernel/patches/README.md`). Reaproveita
conceitualmente o modelo de estados/recompensas do AI-Linux acadêmico
(dissertação de Nathan Loretan, 2018), implementado sobre infraestrutura
de kernel moderna em vez de um patch a `kernel/sched/`.
`kernel/config/sched-ext.fragment` já prepara a opção de kernel
necessária.

## 0.8 — Scheduler adaptativo

Métricas de CPU, memória, latência e tokens/s alimentando decisões do AI
Scheduler — passo em direção ao aprendizado de fato, não apenas regras
fixas.

## 0.9 / 1.0 — Distribuição

Imagem bootável para SSD/pendrive com instalador guiado, modo
`RECOVERY` validado em hardware real (não apenas especificado), e
release reproduzível a partir do código-fonte (`make legal-info` incluído
no processo de release — ver `docs/licenses.md`).
