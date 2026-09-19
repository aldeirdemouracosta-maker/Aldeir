# Arquitetura — IA Linux Minimal

```
┌──────────────────────────────────────────────────┐
│                    IA SHELL                        │  rootfs-overlay/usr/bin/ia-shell
│              prompt interativo "IA>"                │  (cliente fino, BusyBox ash)
├──────────────────────────────────────────────────┤
│  ia-model │ ia-chat │ ia-benchmark │ ia-server │ ia-gpu │ ia-agent │  cliente fino cada um
├──────────────────────────────────────────────────┤
│                    AI-CORE (Rust)                   │  ai-core/
│  hardware.rs │ model.rs │ backend.rs │ config.rs    │  socket Unix
│  agent.rs (AgentManager, fila) │ json.rs │           │  /run/ai-core.sock
│  llama_client.rs │ ipc.rs                            │
├──────────────────────────────────────────────────┤
│         llama.cpp / llama-server (CPU / Vulkan)      │  pacote Buildroot upstream
├──────────────────────────────────────────────────┤
│         AI Resource Manager (cgroups v2, zram)       │  kernel/config (habilitado,
│         DAMON / DAMON_RECLAIM (preparado, 0.6)       │  não gerenciado por agente ainda)
├──────────────────────────────────────────────────┤
│      AI Scheduler — sched_ext + eBPF (0.7, futuro)   │  kernel/config/sched-ext.fragment
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
ROLES|TASK <papel> <texto>|STATUS <id>|LIST`. Ver `ai-core/src/ipc.rs`.

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
│ SYSTEM     512 MiB   │          │ EFI          64 MiB  │
│ RECOVERY   128 MiB   │          │ SYSTEM      512 MiB  │
│ DATA       512 MiB+  │          │ RECOVERY    128 MiB  │
└─────────────────────┘          │ DATA        512 MiB+ │
                                    └─────────────────────┘
```

SYSTEM é montada normalmente leitura-escrita nesta versão (candidata a
`EROFS` somente-leitura numa versão futura — `CONFIG_EROFS_FS` já
habilitado em `kernel/config/ia_linux_x86_64.config`). RECOVERY é
montada somente leitura quando presente. Boot usa `PARTUUID`, não
`/dev/sdaN` — a ordem de detecção de discos físicos não é garantida.
DATA nunca é apagada por uma atualização de SYSTEM — separação
intencional entre sistema operacional e dados do usuário (modelos GGUF,
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

## Acesso remoto (opcional)

`llama-server` (via `ia-server start`) escuta apenas em
`127.0.0.1:8080` por padrão — sem exposição de rede a menos que o
operador reconfigure explicitamente. Ver `rootfs-overlay/usr/bin/ia-server`.
