# ISO do IA-Linux MiniVideo

Sistema inicializável dedicado **somente** à criação e edição de vídeo com
agentes de IA locais. Não inclui chat genérico, criação de aplicativos nem
os serviços `ai-core`/`ia-shell` da base.

> **Estado em 2026-09-24:** configuração validada contra o Buildroot 2026.08
> real e kernel compilado de verdade (veja "O que foi testado"). **O ISO
> completo ainda não foi compilado nem inicializado**: este ambiente de
> desenvolvimento só alcança o GitHub. O workflow
> `.github/workflows/minivideo-iso.yml` compila o ISO e dá boot no QEMU
> no GitHub Actions. Nada foi testado na RX 580 ainda.

## Arquitetura em camadas

```
┌─────────────────────────────────────────────────────────────┐
│ tty1: minivideo-ui (pastas)  ·  tty2/tty3: login  ·  ttyS0  │
├─────────────────────────────────────────────────────────────┤
│ Especialistas: Diretor · Editor · Fiscal · Continuísta      │
│ Agentes: cortador, silencios (auto-editor), audio, cenas,   │
│ transcritor (whisper.cpp), legendas, interpolador (RIFE),   │
│ upscaler (Real-ESRGAN), escala, exportador (x264/VA-API),   │
│ coordenador (llama.cpp + Qwen3) · gerador/editor (CUDA)     │
│ Hardware Safety Guard (somente leitura) sobre cada job GPU  │
├─────────────────────────────────────────────────────────────┤
│ FFmpeg 6.1 · mpv (DRM) · Mesa 26.1 RADV + radeonsi VA-API   │
│ Vulkan loader · ALSA · Python 3 (curses) · glibc 2.44       │
├─────────────────────────────────────────────────────────────┤
│ Kernel 6.18.52 do IA Linux Minimal (config + physical)      │
│ + linux-minivideo.fragment (aditivo: áudio, initrd, fbcon,  │
│   rede, exFAT/NTFS, sensores, preparo APU/NVIDIA)           │
├─────────────────────────────────────────────────────────────┤
│ ISO híbrido isolinux (BIOS) · rootfs inteiro no initramfs   │
└─────────────────────────────────────────────────────────────┘
```

- **Camada 1, `IA_LINUX`:** IA Linux Minimal fixado no commit `cd7c721`
  (branch `claude/dreamy-curie-j1yy53`). Dela vêm a versão do kernel, a
  configuração base e o `physical.fragment`, **sem alteração**.
- **Camada 2, `IA_MINIVIDEO`:** `ia-linux-minivideo/image/`, com defconfig,
  pacotes, overlay e fragmento aditivo.

### Por que ISO com initramfs resolve dois problemas da base

1. **Raiz do sistema:** a imagem de disco da base usa `root=UUID=` sem
   initramfs, algo que o kernel não resolve sozinho. No ISO, a raiz é o
   próprio initramfs e não existe `root=`.
2. **Firmware da RX 580:** na base, o `amdgpu` é embutido (`=y`) e o
   firmware fica no rootfs, que ainda não está montado quando o driver
   sobe. No ISO, `/lib/firmware` já está no initramfs nesse momento.

## Pastas (partição de dados)

O ISO roda da RAM. Para guardar o trabalho, crie **uma vez** uma partição
ext4 com o rótulo `MV_DADOS`, num SSD, HD ou pendrive. Isso apaga a partição
escolhida; confira o dispositivo com `lsblk` antes:

```bash
sudo mkfs.ext4 -L MV_DADOS /dev/sdXN
```

No boot, `S30minivideo` monta essa partição em `/data` e cria
`/data/minivideo/{Projetos,Midia,Modelos,Saidas,Jobs,Logs}`. Sem ela, a
interface mostra um aviso vermelho: os arquivos ficam na RAM e somem ao
desligar.

Onde ficam os modelos:

| Agente | Onde | Vem no ISO? |
|---|---|---|
| Interpolador (RIFE v4.6) | `/usr/share/minivideo/modelos/rife/rife-v4.6` | sim |
| Upscaler (Real-ESRGAN) | `/usr/share/minivideo/modelos/realesrgan/models` | sim |
| Transcritor | `Modelos/whisper/ggml-*.bin` | não (ex.: `ggml-small.bin`) |
| Coordenador | `Modelos/llm/*.gguf` | não (Qwen3-1.7B ou 0.6B) |
| Gerador/editor | via `mini-ia-videos` + CUDA | não (futuro) |

## Menu de boot (isolinux)

| Entrada | Uso |
|---|---|
| IA-Linux MiniVideo (RX 580 / Vulkan) | normal |
| Recuperação: sem GPU (`nomodeset`) | tela preta ou travamento no `amdgpu` |
| Diagnóstico: console serial + tela | logs completos (`loglevel=7`) |

## Como compilar

Pré-requisitos no host (Debian/Ubuntu):
`build-essential git unzip rsync bc cpio file wget patch glslc libelf-dev libssl-dev`.
O `glslc` é obrigatório: o Buildroot 2026.08 não empacota shaderc, e tanto o
llama.cpp quanto o whisper.cpp com Vulkan compilam shaders no host.

```bash
cd ia-linux-minivideo/image
./scripts/build-iso.sh --so-configurar   # configura e valida as opções (minutos)
./scripts/build-iso.sh                   # compila (horas; ~20 GB em ~/minivideo-build)
./scripts/testar-qemu.sh                 # boot em VM com disco MV_DADOS de teste
```

`scripts/validar-config.sh` compara cada linha do defconfig com o `.config`
final. Opção inexistente, oculta ou com dependência faltando vira erro, em
vez de sumir em silêncio.

Gravar no pendrive: `sudo dd if=ia-linux-minivideo.iso of=/dev/sdX bs=4M conv=fsync`
(confira `/dev/sdX` com `lsblk`; isso apaga o pendrive).

## O que foi testado nesta sessão

| Item | Resultado | Como |
|---|---|---|
| Opções do defconfig contra o Buildroot 2026.08 | todas ativas, depois de 3 correções | `build-iso.sh --so-configurar` |
| Kernel 6.18.52 com base + physical + fragmento MiniVideo | `olddefconfig` + **`bzImage` compilado** (12 MB) | árvore estável real |
| Opções do fragmento MiniVideo | todas aplicadas | comparação com o `.config` final |
| Pipeline de agentes (corte, áudio, cenas, RIFE, Real-ESRGAN, exportação) | vídeo 320×180 a 12 fps → 1280×720 a 24 fps com áudio | FFmpeg 6.1 real + Vulkan por software |
| Auto-Editor, RIFE, Real-ESRGAN em CPU **IvyBridge** emulada (seu E5-2630L v2) | sem instrução ilegal | `qemu-x86_64 -cpu IvyBridge` |
| Mesmos binários em CPU **SandyBridge** (E5 v1) | Auto-Editor ok; RIFE e Real-ESRGAN falham, e o Real-ESRGAN aborta dentro do LLVM do llvmpipe (Vulkan por software) | não conclusivo para GPU real |
| Interface de pastas | navegação, ajuda, terminal de prompt, execução de job | pty real + `pyte` |
| ISO completo, boot, RX 580, VA-API, áudio, sensores | **não testado** | pendente (CI e hardware) |

## Defeitos encontrados na base (IA Linux Minimal), não corrigidos lá

1. `BR2_X86_CPU_HAS_AVX=y` / `BR2_X86_CPU_HAS_SSE4=y` são símbolos ocultos
   do Buildroot: no defconfig **não têm efeito**. O certo é escolher a
   variante (`BR2_x86_corei7_avx` ou `BR2_x86_ivybridge`). O ISO usa
   sandybridge.
2. `BR2_TOOLCHAIN_BUILDROOT_WCHAR=y` não existe para glibc (sem efeito).
3. No kernel, `E1000`, `E1000E` e `R8169` são descartados pelo
   `olddefconfig` (faltam `NETDEVICES`, `ETHERNET` e `NET_VENDOR_*`): **sem
   rede cabeada**. O fragmento MiniVideo corrige isso para o ISO.
4. Também são descartados, sem uso no ISO: `BPF_EVENTS`, `CRYPTO_LZ4` e
   `CRYPTO_ZSTD`.
5. `root=UUID=` sem initramfs na imagem de disco (ver
   `INTEGRACAO_IA_LINUX_MINIMAL.md`).
6. O llama.cpp com Vulkan do Buildroot depende do `glslc` do host (não
   declarado).

## Melhorias vindas dos pacotes de pesquisa anexados (X79, RX 580, Vulkan)

| Achado | Aplicado |
|---|---|
| OpenBLAS com `TARGET=SANDYBRIDGE` acelera o llama.cpp na CPU AVX1 | `BR2_PACKAGE_OPENBLAS=y`; o alvo `SANDYBRIDGE` vem da variante `BR2_x86_corei7_avx` (a `sandybridge` do Buildroot não tem alvo OpenBLAS) |
| `llama-bench` para achar threads e camadas na GPU | `minivideo-modelos calibrar <gguf>` grava `Modelos/llm/calibracao.json` |
| RADV/Mesa é a rota da RX 580; AMDVLK é legado; ROCm gfx803 só em laboratório | mantido: só RADV no ISO |
| NVIDIA/CUDA e AMD/Vulkan como workers independentes com roteador | roteador de agentes por dispositivo; nada é dividido entre GPUs |
| Gitleaks/OSV em vez de antivírus residente | job `segredos` (Gitleaks 8.30.1, checksum conferido) na CI; o pacote Python não tem dependências de execução, então o OSV-Scanner não teria o que analisar |
| `GGML_NATIVE=ON` dos scripts X79 | vale para compilar **na própria máquina**; no ISO (compilação cruzada) o ggml usa o `-march` da variante escolhida |
| Servidores de arquivos web (dufs etc.) | não usados: a interface de pastas roda no console, sem abrir porta de rede |

O autoteste de boot (`minivideo.autoteste=1`) agora também roda os
especialistas (dry-run, edição de duas cenas e reprodução pelo `job.json`)
e o `minivideo-modelos catalogo`.

## Preparado para hardware futuro

| Hardware | Já no ISO | Falta |
|---|---|---|
| **APU AMD** (Ryzen com gráficos integrados) | amdgpu + firmware, RADV, `CPU_SUP_AMD`, `AMD_IOMMU`, `k10temp`; agentes classificam `vulkan-apu` (memória compartilhada, sem barrar por VRAM) | teste em hardware; limite de GTT no Safety Guard |
| **NVIDIA/CUDA** (16 GB alvo, 12 GB mínimo) | `nouveau` desligado, `MODULES=y`; agentes classificam `cuda` e exigem ≥12 GB; backend NVIDIA do Guard (`nvidia-smi`) | pacote próprio com os módulos abertos da NVIDIA e o espaço de usuário CUDA (o `nvidia-driver` do Buildroot é o legado 390.151); PyTorch/diffusers para Wan/LTX; partição de dados maior |
| **UEFI sem CSM** (placas novas) | — | segunda variante com GRUB EFI (o ISO isolinux atual só dá boot em BIOS/legado) |
| **GPUs mistas** | cada GPU é um dispositivo independente; roteamento dGPU → APU → CUDA | escalonador por dispositivo com limite de memória |
