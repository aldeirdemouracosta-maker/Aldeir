# Arquitetura — IA Linux Minimal

```
┌──────────────────────────────────────────────────┐
│                    IA SHELL                        │  rootfs-overlay/usr/bin/ia-shell
│              prompt interativo "IA>"                │  (cliente fino, BusyBox ash)
├──────────────────────────────────────────────────┤
│ ia-model│ia-chat│ia-benchmark│ia-server│ia-gpu│ia-agent│ia-memory│ia-scheduler│  cliente fino
├──────────────────────────────────────────────────┤
│                    AI-CORE (Rust)                   │  ai-core/
│  hardware.rs │ model.rs │ backend.rs │ config.rs    │  socket Unix
│  agent.rs (AgentManager, fila) │ memory.rs           │  /run/ai-core.sock
│  scheduler.rs │ telemetry.rs │ json.rs                │
│  llama_client.rs │ ipc.rs                             │
├──────────────────────────────────────────────────┤
│         llama.cpp / llama-server (CPU / Vulkan)      │  pacote Buildroot upstream
├──────────────────────────────────────────────────┤
│   AI Resource Manager — cgroups v2 memory.low +      │  kernel/config: CONFIG_MEMCG,
│   cpu.weight; DAMON_RECLAIM por perfil (ai-core)     │  CONFIG_FAIR_GROUP_SCHED,
│   (mesmo cgroup para memória e CPU do modelo)        │  CONFIG_DAMON_RECLAIM (0.6/0.7)
├──────────────────────────────────────────────────┤
│  sched_ext + eBPF de verdade — adiado (ver 0.7 nos   │  kernel/config/sched-ext.fragment
│  docs; requer bpftool/kernel real, não disponíveis   │  (preparado, desligado)
│  neste ambiente de desenvolvimento)                  │
├──────────────────────────────────────────────────┤
│                Linux 6.18.52 LTS                     │  kernel/config/
├──────────────────────────────────────────────────┤
│           Buildroot 2026.08 + BusyBox                │  buildroot/
└──────────────────────────────────────────────────┘
```

## Por que o "cérebro" fica em user-space

O kernel nunca hospeda decisões de IA diretamente. `ai-core` roda em anel
3; se o processo inteiro travar (não apenas uma tarefa de agente — ver
seção seguinte), `ai-core` reinicia — supervisionado por `respawn` no
`inittab` (ver
`rootfs-overlay/etc/inittab`) — sem derrubar o sistema. Essa é a razão
pela qual este projeto não porta literalmente o patch de kernel do
AI-Linux acadêmico (dissertação de mestrado de Nathan Loretan, MSc
University of Glasgow) — ver `kernel/patches/README.md` para a discussão
completa.

## Um binário, dois papéis: `ai-core`

`ai-core` sem argumentos roda como **servidor**: detecta hardware uma vez
na inicialização, abre `/run/ai-core.sock` e atende conexões (uma
thread por conexão). `ai-core <COMANDO...>` com argumentos roda como
**cliente**: conecta no socket, envia o comando, imprime a resposta e
sai. Isso evita depender de suporte a socket Unix em `busybox nc`, que
não é garantido em toda configuração do BusyBox — ver
`ai-core/src/main.rs` (`run_server` / `run_client`).

Protocolo (texto, uma linha por comando, resposta terminada por uma
linha `.`): `PING`, `VERSION`, `STATUS`, `HW`, `MODEL LIST|ACTIVE|SELECT
<n>|RECOMMEND`, `BACKEND GET|SET <auto|cpu|vulkan>`, `AGENT
ROLES|TASK <papel> <texto>|STATUS <id>|LIST`, `MEMORY
STATUS|APPLY|PROTECT <bytes>`, `SCHED STATUS|APPLY|ADAPT`. Ver
`ai-core/src/ipc.rs`.

## Seleção de backend (CPU/Vulkan) — AUTO

```
modo configurado (auto/cpu/vulkan)
          │
          ▼
   cpu?  ──► sempre CPU
   vulkan? ─► GPU AMD pronta? ──sim──► Vulkan
                    │
                    não
                    ▼
                   CPU (fallback)
   auto?  ──► mesma lógica de "vulkan"
```

`vulkan` explícito sem GPU pronta nunca falha — cai para CPU
automaticamente (`ai-core/src/backend.rs::resolve`). "GPU pronta"
significa: `/sys/class/drm/card*/device/vendor` reporta `0x1002` (AMD) **e**
o render node correspondente existe em `/dev/dri`.

QEMU é intencionalmente CPU-only (sem GPU virtual/Venus/VirGL) nesta
série 0.x — ver `buildroot/configs/ia_linux_qemu_x86_64_defconfig`.
Hardware físico usa Mesa RADV (GCN/RDNA, sem exigir ROCm) — ver
`hardware/amd/README.md`.

## Disco (alvos físicos)

```
BIOS                              UEFI
┌─────────────────────┐          ┌─────────────────────┐
│ SYSTEM    2560 MiB   │          │ EFI          64 MiB  │
│ RECOVERY   128 MiB   │          │ SYSTEM     2560 MiB  │
│ DATA       (ajustável)│         │ RECOVERY    128 MiB  │
└─────────────────────┘          │ DATA        (ajustável)│
                                    └─────────────────────┘
```

O tamanho de DATA é fixo em `size = ...` em `genimage-bios.cfg`/
`genimage-uefi.cfg` — não cresce sozinho para preencher o disco de
destino. Está atualmente em `96G`, dimensionado para um SSD "de
110 GB" (fabricante usa GB decimal; o SO relata ~102,4 GiB reais —
`96G` + partições fixas deixa ~5,7 GiB de margem). Para outro
dispositivo, edite `size` nesses dois arquivos antes de compilar.

SYSTEM é montada normalmente leitura-escrita nesta versão (candidata a
`EROFS` somente-leitura numa versão futura — `CONFIG_EROFS_FS` já
habilitado em `kernel/config/ia_linux_x86_64.config`). RECOVERY é
montada somente leitura quando presente. Boot usa o UUID do sistema de
arquivos da partição SYSTEM (`root=UUID=...` no `grub.cfg`, fixo e
gravado no ext4 por `post-image.sh` via `tune2fs -U` antes de montar o
disco final — não um PARTUUID nem `/dev/sdaN`, cuja ordem de detecção
em boot físico não é garantida). Usar um UUID fixo, gerado por nós
mesmos, evita depender de um passo de template em tempo de build — ver
o comentário em `buildroot/board/ia-linux/grub.cfg` para o histórico de
por que a versão anterior (um placeholder nunca substituído) não
funcionava. DATA nunca é apagada por uma atualização de SYSTEM —
separação intencional entre sistema operacional e dados do usuário
(modelos GGUF,
sessões, workspace).

## Multiagente: fila única, um worker, um modelo carregado

```
                    ┌── tarefa (planejador)
                    ├── tarefa (programador)
AgentManager ───────┼── tarefa (pesquisador)     fila FIFO, 1 worker thread
(ai-core/src/       ├── tarefa (crítico)         processa sequencialmente
 agent.rs)          └── tarefa (executor)
                              │
                              ▼
                     llama_client::complete()
                              │
                              ▼
                POST /completion — llama-server
                     (127.0.0.1:8080, 1 modelo)
```

`AGENT TASK <papel> <texto>` enfileira e retorna um id imediatamente
(nunca bloqueia); `AGENT STATUS <id>` consulta o resultado depois
(`queued`/`running`/`done`/`error`). Um único worker thread processa a
fila em ordem de chegada (FIFO, sem prioridades ainda) — decisão
deliberada: em hardware modesto, várias tarefas disputando o mesmo
modelo ao mesmo tempo não trariam ganho real, só disputa por RAM/CPU. Se
`llama-server` não estiver rodando (`ia-server start`), a tarefa termina
com `status=error` e a mensagem de conexão — `ai-core` nunca tenta subir
o `llama-server` sozinho.

`json.rs`/`llama_client.rs` são escritos à mão sobre `std::net::TcpStream`
(sem crates externos, para manter a cross-compilação via Buildroot
simples) — ver os comentários desses módulos para as limitações
conhecidas do parser JSON (não é um parser genérico, só o suficiente
para o campo `content` de nível superior que o `llama.cpp` retorna).

## AI Memory: DAMON_RECLAIM por perfil + proteção via cgroup v2

Duas responsabilidades separadas em `ai-core/src/memory.rs`, acionadas
por `MEMORY APPLY` (que `ia-server start` já chama automaticamente,
melhor esforço, após escrever `/run/ia-server.pid`):

```
MEMORY APPLY
     │
     ├──► damon_reclaim: enabled/min_age/quota_ms/quota_sz
     │    ajustados por Profile (TINY/LOW/MEDIUM/LARGE) —
     │    /sys/module/damon_reclaim/parameters (IA_DAMON_SYSFS)
     │
     └──► cgroup: lê PID de /run/ia-server.pid (IA_RUN_DIR),
          calcula floor = tamanho_do_gguf_ativo × IA_MEM_FLOOR_PERCENT/100
          (padrão 150%), escreve memory.low no cgroup de proteção
          — /sys/fs/cgroup/ia-linux/model/ (IA_CGROUP_ROOT)
```

A regra de negócio ("RAM do modelo/KV cache nunca é candidata a reclaim
agressivo; logs/cache/agentes inativos sim") é implementada com
`memory.low` de cgroup v2 no processo do `llama-server`, não com os
filtros de memcg do próprio DAMON — que existem, mas exigem a hierarquia
sysfs completa de kdamonds/contexts/schemes, bem mais complexa. `memory.low`
é o mecanismo padrão do kernel para proteger a memória de um cgroup sob
pressão, e cobre tanto reclaim comum quanto o reclaim proativo do
DAMON_RECLAIM (que reutiliza o caminho comum de reclaim do kernel).

Cada peça falha de forma independente e não fatal: se `damon_reclaim`
não estiver carregado, `MEMORY APPLY` reporta isso e segue tentando a
proteção via cgroup; se `ia-server` não estiver rodando, reporta "nada a
proteger" em vez de erro. `MEMORY STATUS` sempre reflete o estado real
(`disponível`/`indisponível`, floor atual, PIDs protegidos).

Nota honesta de escopo: este ambiente de desenvolvimento não tem
`/sys/module/damon_reclaim` nem cgroup v2 montados — a validação foi
feita com diretórios temporários simulando a mesma estrutura de
arquivos simples do kernel (65 testes unitários), mais um smoke test
manual ponta a ponta. Ver `ai-core/src/memory.rs` para a justificativa
completa e `docs/build.md` para o que foi e não foi validado.

## AI Scheduler: cpu.weight no mesmo cgroup da AI Memory (sched_ext adiado)

```
SCHED APPLY
     │
     └──► cgroup: memory::protected_cgroup_dir(cgroup_root) — o MESMO
          diretório que MEMORY APPLY já usa para memory.low — recebe
          cpu.weight escalado por Profile:
              TINY  → 800   (8× o padrão de 100)
              LOW   → 600
              MEDIUM→ 400
              LARGE → 200   (mais perto do padrão — sobra CPU)
```

O plano original desta etapa era um scheduler `sched_ext`/eBPF completo
— carregado/removido dinamicamente, com fallback automático para o
scheduler padrão do Linux, reaproveitando o modelo de
estados/recompensas da dissertação do AI-Linux (ver
`kernel/patches/README.md`). Ao chegar aqui, confirmamos que este
ambiente de desenvolvimento tem `clang`, mas não tem `bpftool`, não tem
`/sys/kernel/sched_ext` e não tem cgroup v2 — não haveria como
compilar, carregar nem testar um scheduler BPF de verdade. Mesma
decisão já tomada para a AI Memory (0.6): em vez de fingir essa
validação, a 0.7 entrega `cpu.weight` de cgroup v2 — mecanismo padrão
do kernel, simples, testável com diretórios simulando cgroupfs (ver
`ai-core/src/scheduler.rs`, com testes cobrindo inclusive o
compartilhamento do mesmo diretório de cgroup entre `memory.rs` e
`scheduler.rs`).

`cpu.weight` e `memory.low` convivem no mesmo cgroup porque protegem o
mesmo processo pelo mesmo motivo: o `llama-server` executando o modelo
ativo merece prioridade tanto de RAM (não ser vítima de reclaim
agressivo) quanto de CPU (não perder fatias de tempo de processamento
para processos auxiliares) sob contenção. Um scheduler `sched_ext` de
verdade — com decisões por tarefa/agente, não só um peso estático por
cgroup — continua sendo trabalho futuro explícito, não descartado; ver
a decisão completa em `kernel/patches/README.md`.

## Scheduler adaptativo: telemetria real + regra determinística (não ML)

```
SCHED ADAPT
     │
     ├──► telemetry::collect() — /proc/loadavg, /proc/meminfo
     │    (leitura REAL — sem caminho parametrizável, ao contrário de
     │    memory.rs/scheduler.rs; /proc existe neste sandbox de verdade)
     │
     ├──► AgentManager::tokens_per_second_stats(3) — média das últimas
     │    3 tarefas concluídas + melhor tokens/s desta sessão do daemon
     │    (extraído de timings.predicted_per_second do llama-server —
     │    ver llama_client::CompletionResult)
     │
     └──► telemetry::adapt_weight(...) — regra determinística:
            throughput caiu + CPU contendida + memória OK → +50% (cap 2000)
            throughput bom + CPU ociosa                   → volta ao peso base
            caso contrário                                 → mantém peso atual
          → scheduler::apply_weight_value() se o peso mudou
```

Diferente de `SCHED APPLY` (0.7, peso fixo por perfil), `SCHED ADAPT`
reage ao que está realmente acontecendo no sistema. Mas é importante ser
preciso sobre o que isso é e não é: **é uma regra se-então determinística,
não aprendizado por reforço nem qualquer forma de ML**. O roadmap descreve
esta etapa como "um passo em direção ao aprendizado, não apenas regras
fixas" — é exatamente isso: telemetria real substituindo um valor
estático, não um agente que aprende a partir de recompensa observada.

Vale notar uma assimetria interessante com as etapas anteriores: a
telemetria desta etapa (`/proc/loadavg`, `/proc/meminfo`) **foi validada
contra o kernel real** deste ambiente de desenvolvimento — diferente do
DAMON_RECLAIM (0.6) e do cgroup v2 (0.7), que precisaram de diretórios
temporários simulando sysfs/cgroupfs porque não existem aqui. `/proc`
sempre existeu neste sandbox (mesma base que `hardware.rs` já usa desde
a 0.4); só o mecanismo de *efeito* (`cpu.weight` em cgroup v2) continua
simulado nos testes, pela mesma razão da 0.7.

Um smoke test manual confirmou o pipeline completo: telemetria real
(`load1=0.25`, `mem_disponivel_pct=96.2`) combinada com tokens/s reais de
um `llama-server` de mentira (50.0 → 8.0 → 7.5 tokens/s, média recente
21.8, melhor 50.0 — ambos calculados corretamente pela regra) resultou
em manter o peso, porque não havia contenção real de CPU neste
ambiente — decisão correta segundo a regra.

## Acesso remoto (opcional)

`llama-server` (via `ia-server start`) escuta apenas em
`127.0.0.1:8080` por padrão — sem exposição de rede a menos que o
operador reconfigure explicitamente. Ver `rootfs-overlay/usr/bin/ia-server`.
