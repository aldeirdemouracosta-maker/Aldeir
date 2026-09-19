# Changelog — IA Linux Minimal

## 0.4.0-alpha5 — AI Core (Rust)

- Novo daemon `ai-core` em Rust, substituindo os scripts shell como
  coordenador central de hardware, modelos e backend.
- IPC via socket Unix (`/run/ia-core.sock`), protocolo texto linha-a-linha
  (`STATUS`, `HW`, `MODEL LIST`, `MODEL SELECT <n>`, `BACKEND <auto|cpu|vulkan>`).
- `ia-shell` (BusyBox ash) passa a ser um cliente fino que fala com o
  `ai-core` em vez de reimplementar a lógica em shell.
- Detecção de hardware (CPU/RAM/GPU) movida de `hardware/detect.sh` para o
  módulo `hardware.rs`, mantendo o script shell como fallback de
  recuperação (modo `RECOVERY`).
- Pacote Buildroot `package/ai-core` (Config.in + .mk) para compilar o
  daemon via `cargo` cross-compilado durante o build do Buildroot.
- Testes unitários Rust para parsing de `/proc/cpuinfo`, `/proc/meminfo` e
  seleção de perfil (TINY/LOW/MEDIUM/LARGE).

## 0.3.0-alpha4 — Vulkan/RADV

- Mesa RADV + Vulkan Loader + `vulkaninfo` habilitados no Buildroot.
- `llama.cpp` compilado com backend Vulkan além de CPU.
- Comando `ia-gpu` (status/list/vulkaninfo) e seleção de backend
  `auto|cpu|vulkan` com fallback automático para CPU.
- `ia-benchmark` ganha `cpu`, `vulkan`, `compare`.
- Firmware AMDGPU (`linux-firmware`) habilitado; QEMU permanece CPU-only
  intencionalmente (sem GPU virtual).

## 0.2.0-alpha3 — Inferência em CPU

- Integração do pacote oficial Buildroot `llama.cpp` (`llama-cli`,
  `llama-server`, `llama-bench`).
- Comandos `ia-model` (list/select/active/recommend), `ia-chat`,
  `ia-benchmark`, `ia-server` (start/status/stop, bind em `127.0.0.1:8080`).
- Perfis automáticos por RAM: TINY (<6GB), LOW (6–12GB), MEDIUM (12–24GB),
  LARGE (24GB+), com threads/contexto/batch calculados.
- `/data/config/runtime.conf` para overrides manuais.
- Modelos GGUF mantidos fora da imagem do sistema, em `/data/models`.

## 0.1.1-alpha2 — Hardware físico

- Perfis BIOS (legado) e UEFI 64-bit com GRUB 2.
- Particionamento SYSTEM/RECOVERY/DATA (+ EFI no perfil UEFI).
- Boot por `PARTUUID` em vez de `/dev/sdaN` fixo.
- Drivers SATA/AHCI, NVMe, USB, teclado, rede Intel/Realtek, AMDGPU/Radeon.
- Modo de boot seguro `nomodeset`; RECOVERY montada somente leitura.

## 0.1.0-alpha1 — Boot mínimo

- BR2_EXTERNAL inicial, alvo QEMU x86_64.
- BusyBox + glibc, kernel Linux 6.18.52 LTS fixado.
- cgroups v2, BPF/eBPF e zram habilitados; fragmento `sched_ext`
  preparado, porém desligado por padrão.
- Console somente texto, prompt `IA>`.
- `/data/{models,rag,agents,workspace,sessions,logs}` como área persistente
  separada do sistema.
