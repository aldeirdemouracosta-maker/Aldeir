# kernel/patches/

Nenhum patch de kernel está aplicado nesta versão. O IA Linux Minimal usa
o Linux 6.18.52 LTS upstream, configurado por `kernel/config/` (base +
fragments), sem tocar no código-fonte do kernel.

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

## AI Scheduler (etapa 0.7): por que cpu.weight, não sched_ext ainda

O plano original para a 0.7 era exatamente o que o parágrafo acima
descreve: um programa BPF + um agente Rust em user-space carregados via
sched_ext. Ao chegar nessa etapa, checamos o ambiente onde este projeto
é desenvolvido e ele tem `clang`, mas **não** tem `bpftool`, **não** tem
`/sys/kernel/sched_ext` (o kernel deste sandbox não expõe sched_ext
ativo) e **não** tem cgroup v2 montado. Não haveria como compilar,
carregar nem testar um scheduler BPF de verdade aqui — e este projeto
não finge ter validado algo que não rodou.

Decisão, com o mesmo raciocínio já aplicado à AI Memory (0.6, DAMON): em
vez de um scheduler `sched_ext` completo, a 0.7 entrega o controlador
`cpu` de cgroup v2 (`cpu.weight`) — mecanismo padrão do kernel, bem mais
simples, e que dá para testar de verdade com diretórios simulando a
estrutura de cgroupfs (ver `ai-core/src/scheduler.rs`). `cpu.weight` do
cgroup do modelo/llama-server é ajustado por perfil de hardware (mesmo
cgroup que `memory.rs` já protege com `memory.low`), priorizando CPU
para a inferência sem precisar de BPF nem de sched_ext.

Um scheduler `sched_ext` de verdade — reaproveitando o modelo de
estados/recompensas da dissertação — continua sendo trabalho futuro
explícito, não descartado: exige um kernel com `CONFIG_SCHED_CLASS_EXT`
ativo, `bpftool` para gerar `vmlinux.h` a partir do BTF, e um loader BPF
(`libbpf` ou equivalente), nenhum dos quais está disponível/verificável
neste ambiente de desenvolvimento. `kernel/config/sched-ext.fragment`
já prepara a opção de kernel necessária, desligada por padrão, para
quando essa etapa futura for retomada com acesso a um kernel real.

Se algum patch vier a ser necessário no futuro (por exemplo, um driver
específico, ou eventualmente o próprio scheduler sched_ext), ele será
adicionado aqui como `NNNN-descricao.patch` (formato `git format-patch`),
sob GPL-2.0-only — ver `docs/licenses.md`.
