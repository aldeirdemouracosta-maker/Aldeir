# Arquitetura — IA Linux Minimal

```
┌──────────────────────────────────────────────────┐
│                    IA SHELL                        │  rootfs-overlay/usr/bin/ia-shell
│              prompt interativo "IA>"                │  (cliente fino, BusyBox ash)
├──────────────────────────────────────────────────┤
│  ia-model │ ia-chat │ ia-benchmark │ ia-server │ ia-gpu │  cliente fino cada um
├──────────────────────────────────────────────────┤
│                    AI-CORE (Rust)                   │  ai-core/
│  hardware.rs │ model.rs │ backend.rs │ config.rs    │  socket Unix
│  agent.rs (placeholder 0.5) │ ipc.rs                 │  /run/ai-core.sock
├──────────────────────────────────────────────────┤
│               llama.cpp (CPU / Vulkan)               │  pacote Buildroot upstream
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
3; se um agente (futuro, etapa 0.5) cometer um erro, `ai-core` reinicia —
supervisionado por `respawn` no `inittab` (ver
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
<n>|RECOMMEND`, `BACKEND GET|SET <auto|cpu|vulkan>`. Ver
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

## Modelos e agentes compartilham um único modelo carregado

```
              ┌── (0.5, futuro) agente planejador
              ├── (0.5, futuro) agente programador
llama.cpp ────┼── (0.5, futuro) agente pesquisador
(1 modelo)    ├── (0.5, futuro) agente crítico
              └── (0.5, futuro) agente executor
```

Nesta versão (0.4) `ai-core` gerencia hardware, modelos e backend, mas
ainda **não** implementa múltiplos agentes — `agent.rs` é um placeholder
que documenta a interface planejada e faz `STATUS` reportar
honestamente "não implementado" em vez de simular a funcionalidade.

## Acesso remoto (opcional)

`llama-server` (via `ia-server start`) escuta apenas em
`127.0.0.1:8080` por padrão — sem exposição de rede a menos que o
operador reconfigure explicitamente. Ver `rootfs-overlay/usr/bin/ia-server`.
