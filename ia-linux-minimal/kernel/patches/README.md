# kernel/patches/

Nenhum patch de kernel está aplicado nesta versão (0.4.0-alpha5). O IA
Linux Minimal usa o Linux 6.18.52 LTS upstream, configurado por
`kernel/config/` (base + fragments), sem tocar no código-fonte do kernel.

## Por que não portamos o AI-Linux (dissertação de mestrado, 2018)

O AI-Linux de Nathan Loretan (MSc, University of Glasgow) substituía
`kernel/sched/fair.c` por `kernel/sched/smart.c` em um Linux 4.17.2, usando
aprendizado por reforço para escalonamento e balanceamento de carga.

Portar esse patch literalmente exigiria reescrevê-lo contra uma arquitetura
de scheduler completamente diferente: o CFS de 2018 foi substituído por
EEVDF a partir do Linux 6.6, e a estrutura interna de `fair.c` mudou
substancialmente desde então.

Em vez de portar o patch, este projeto reaproveita as **ideias** da
dissertação (modelo de estados, recompensas, métricas de decisão) sobre uma
infraestrutura moderna que não exige modificar o kernel:

- **sched_ext** (upstream desde o Linux 6.12): permite implementar um
  scheduler completo em BPF, carregado/removido dinamicamente, com
  fallback automático para o scheduler padrão em caso de falha.
- **DAMON / DAMON_RECLAIM** (já habilitado em `ia_linux_x86_64.config`):
  monitoramento leve de padrões de acesso à memória, para decisões de
  reclaim mais informadas do que mexer diretamente no código antigo de
  reclaim do Linux 4.17.

Quando o AI Scheduler experimental (etapa 0.7 do roadmap, ver
`docs/roadmap.md`) for implementado, ele será um programa BPF + um agente
Rust em user-space carregados via sched_ext — não um patch ao
`kernel/sched/`. `kernel/config/sched-ext.fragment` já prepara a opção de
kernel necessária, mas permanece desligada por padrão até essa etapa.

Se algum patch vier a ser necessário no futuro (por exemplo, um driver
específico), ele será adicionado aqui como `NNNN-descricao.patch`
(formato `git format-patch`), sob GPL-2.0-only — ver `docs/licenses.md`.
