# IA Linux Minimal

Sistema operacional Linux mínimo, **somente texto**, construído para executar
inferência de IA local (modelos GGUF via `llama.cpp`) em hardware modesto,
sem interface gráfica, sem nuvem e sem dependências obrigatórias de
Python/Docker/Ollama.

```
IA>
```

## Estado atual

| Versão | Codinome | Conteúdo |
|---|---|---|
| 0.1.0-alpha1 | boot mínimo | Buildroot + BusyBox + kernel + console + IA Shell |
| 0.1.1-alpha2 | hardware físico | GRUB BIOS/UEFI, partições SYSTEM/RECOVERY/DATA, drivers AMD/Intel |
| 0.2.0-alpha3 | inferência CPU | llama.cpp (CPU), gerenciador de modelos GGUF, perfis de hardware |
| 0.3.0-alpha4 | Vulkan/RADV | Mesa RADV, llama.cpp Vulkan, fallback automático CPU |
| 0.4.0-alpha5 | AI Core | daemon Rust (`ai-core`), IPC via socket Unix, ia-shell fala com o daemon |
| 0.5.0-alpha6 | Multiagente | fila de tarefas (`AgentManager`), cliente HTTP para llama-server, `ia-agent` |
| 0.6.0-alpha7 | AI Memory | DAMON_RECLAIM por perfil + proteção via cgroup v2 (`memory.low`), `ia-memory` |
| 0.7.0-alpha8 | AI Scheduler | prioridade de CPU via cgroup v2 (`cpu.weight`), `ia-scheduler` — sched_ext real fica para depois, ver `kernel/patches/README.md` |
| 0.8.0-alpha9 | Scheduler adaptativo | telemetria real (`/proc`) + tokens/s ajustando `cpu.weight` por uma regra determinística — não é ML, ver `ai-core/src/telemetry.rs` |
| 0.9.0-alpha10 | Instalador + release | `install-to-device.sh` (com salvaguardas) e `make-release.sh` (gates + legal-info + checksums) — validação em hardware real fica para quem gravar de verdade, ver `docs/roadmap.md` |
| 1.0 | *bloqueada* | requer rodar o pipeline completo contra a árvore Buildroot real — sem acesso à internet neste ambiente, ver `CHANGELOG.md` |

**Fechamento desta fase de desenvolvimento**: a série 0.1–0.9 está
completa — código, testes e documentação. É uma árvore de código
testada em tudo que dava para testar sem Buildroot/kernel real neste
ambiente (ver "Encerramento da série 0.x" em `CHANGELOG.md` para o
resumo honesto do que foi e não foi validado), não ainda uma imagem que
alguém rodou. A 1.0 exige o build completo contra a árvore Buildroot
real, fora do alcance deste sandbox.

## Filosofia

- **Somente texto.** Sem X11, Wayland, GNOME, KDE, LXQt.
- **Modelos separados do sistema.** GGUF fica em `/data/models`, nunca dentro
  da imagem do SO.
- **CPU ou Vulkan, nunca ROCm como dependência obrigatória.** Mesa RADV
  cobre GCN/RDNA sem exigir pilha ROCm.
- **Cérebro em user-space.** O agente de IA roda em `ai-core` (Rust,
  anel 3). O kernel nunca hospeda decisões de IA diretamente — evita que um
  erro de agente derrube o sistema inteiro.
- **Reprodutível.** Buildroot 2026.08 + Linux 6.18 LTS congelados como
  plataforma de referência da série 0.x.

## Estrutura

```
ia-linux-minimal/
├── buildroot/            # BR2_EXTERNAL: defconfig, genimage, board files
├── kernel/                # fragmento de config + patches (sched_ext etc.)
├── package/               # pacotes Buildroot próprios (ai-core, ai-shell)
├── ai-core/                # daemon Rust: hardware, modelos, backend, IPC
├── rootfs-overlay/        # arquivos injetados no rootfs final
├── hardware/               # scripts de detecção por fabricante
├── models/                 # perfis e documentação de modelos GGUF
├── configs/                # exemplos de runtime.conf (low-end, medium, vulkan)
├── scripts/                # fetch/configure/compile/run/validate
├── LICENSES/               # ponteiros para o texto completo das licenças
└── docs/                   # arquitetura, build, licenças, roadmap
```

Ver `docs/architecture.md` para o diagrama completo e `docs/roadmap.md`
para as etapas 0.5-1.0 planejadas.

## Build (host com acesso à internet)

```sh
cd ia-linux-minimal
./build.sh qemu     # ou: ./build.sh bios | ./build.sh uefi
./scripts/run-qemu.sh
```

Ver `docs/build.md` para o passo a passo completo, incluindo instalação
física (`bios`/`uefi`) e o que já foi validado versus o que ainda precisa
ser confirmado no seu host (este ambiente de desenvolvimento não teve
acesso a `buildroot.org`). Resumo: `ai-core` foi compilado, testado
(102 testes) e passou em `cargo clippy -- -D warnings`; todos os scripts
shell passaram em `shellcheck`; as opções Buildroot seguem a convenção de
nomes 2026.08 mas não foram confirmadas símbolo-a-símbolo — rode
`scripts/validate-buildroot-configs.sh` antes do primeiro build.

## Licenciamento

Ver `docs/licenses.md`. Resumo: modificações de kernel em GPL-2.0-only;
`ai-core` e `ai-shell` em Apache-2.0; `linux-firmware` (blobs AMDGPU) é
redistribuível mas não é código-fonte aberto.
