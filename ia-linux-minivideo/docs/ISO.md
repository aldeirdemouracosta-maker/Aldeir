# ISO do IA-Linux MiniVideo

Sistema inicializável dedicado **somente** à criação e edição de vídeo com
agentes de IA locais. Não inclui chat genérico, criação de aplicativos nem
os serviços `ai-core`/`ia-shell` da base.

> **Estado em 2026-09-24:** o ISO completo compila no GitHub Actions
> (workflow `.github/workflows/minivideo-iso.yml`) e passa no autoteste e
> no boot BIOS e UEFI no QEMU (runs 36015350849, 36022545484 e 36030083147).
> A versão 0.4 (squashfs, Wi-Fi, variante Ivy Bridge, OpenBLAS, release
> assinado) foi testada aqui em partes (veja "O que foi testado") e é
> validada inteira pela CI. Nada foi testado na RX 580 ainda.

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
│ ISO híbrido: isolinux (BIOS) + GRUB EFI (UEFI)              │
│ initramfs mínimo → live/rootfs.squashfs + overlay na RAM    │
└─────────────────────────────────────────────────────────────┘
```

- **Camada 1, `IA_LINUX`:** IA Linux Minimal fixado no commit `cd7c721`
  (branch `claude/dreamy-curie-j1yy53`). Dela vêm a versão do kernel, a
  configuração base e o `physical.fragment`, **sem alteração**.
- **Camada 2, `IA_MINIVIDEO`:** `ia-linux-minivideo/image/`, com defconfig,
  pacotes, overlay e fragmento aditivo.

### Sistema em squashfs + initramfs mínimo (versão 0.4)

Até a 0.3, o sistema inteiro ia descompactado para a RAM (initramfs). Agora:

1. `/boot/initrd` é um **initramfs mínimo**: busybox, firmware e
   `board/minivideo/live-init`.
2. O init acha o ISO (CD, pendrive, SATA, NVMe; espera até 30 s pelo USB),
   monta `live/rootfs.squashfs` (zstd, somente leitura) com uma camada de
   escrita **overlay em tmpfs** e faz `switch_root`.
3. O initramfs, com o firmware, é apagado no `switch_root`, e a RAM volta a
   ficar livre. Do sistema, só fica na RAM o que for lido (cache) ou
   escrito.
4. `minivideo.toram=1` (entrada "carregar tudo na RAM" do menu) copia o
   squashfs para a RAM. Com isso, dá para tirar o pendrive depois do boot.
5. Sem o ISO, o init avisa e abre um shell de recuperação, em vez de travar.

Os dois problemas da base continuam resolvidos:
- **Raiz sem `root=UUID=`:** o initramfs acha o sistema sozinho.
- **Firmware do `amdgpu` embutido (`=y`):** está no initramfs quando o
  driver sobe.

As montagens ficam visíveis em `/live/{iso,sq,rw,ram}`.

## Pastas (partição de dados)

O que é escrito fora de `/data` fica na RAM e some ao desligar. Para guardar
o trabalho, prepare **uma vez** um disco com a partição de dados:

1. Na interface, tecla **Q**, depois **[p]**. Ou `minivideo-preparar-disco` como root.
2. Ele lista os discos com modelo, tamanho e partições atuais.
3. Recusa o disco de boot, discos com partição montada e discos com menos
   de 8 GiB.
4. Exige que você digite `APAGAR <disco>`.
5. Cria GPT + ext4 com o rótulo `MV_DADOS` e monta na hora.

**Isso apaga o disco escolhido.**

No boot, `S30minivideo` monta essa partição em `/data` e cria
`/data/minivideo/{Projetos,Midia,Modelos,Ferramentas,Saidas,Jobs,Logs}`. Sem ela, a
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

## Boot: BIOS/legado e UEFI no mesmo ISO

O mesmo arquivo dá boot em BIOS/legado (CSM) e em UEFI, gravado em CD ou em
pendrive:

- **BIOS/legado:** isolinux (menu abaixo), como antes.
- **UEFI:** o `board/minivideo/post-image.sh` refaz o ISO do Buildroot com
  uma segunda entrada El Torito, uma imagem FAT (`/boot/efiboot.img`) com
  o GRUB EFI (`BOOTX64.EFI`). Com `-isohybrid-gpt-basdat`, essa imagem
  também vira partição EFI quando o ISO é gravado no pendrive com `dd`. O
  GRUB acha o ISO pelo arquivo `/boot/minivideo-uefi.id` e carrega o menu
  de `/boot/grub/grub.cfg` (`board/minivideo/grub-uefi.cfg`), que tem as
  mesmas três entradas.
- **Kernel:** o fragmento MiniVideo liga `EFI`, `EFI_STUB` e o framebuffer
  do firmware (`SYSFB_SIMPLEFB` + `DRM_SIMPLEDRM`). Sem isso a tela fica
  preta em UEFI até o `amdgpu` assumir, e no modo de recuperação
  (`nomodeset`) fica preta para sempre.
- **Secure Boot:** o GRUB não é assinado. Se a placa tiver Secure Boot,
  desative-o no firmware (placas X79 em geral não têm).

Por que não o modo "grub2" do próprio Buildroot: ele gera ISO só para CD
(`BR2_TARGET_ROOTFS_ISO9660_HYBRID` exige isolinux), e a imagem precisa
dar boot também em pendrive.

### Menu de boot

| Entrada | Uso |
|---|---|
| IA-Linux MiniVideo (RX 580 / Vulkan) | normal |
| IA-Linux MiniVideo - carregar tudo na RAM | `minivideo.toram=1`: dá para tirar o pendrive |
| Recuperação: sem GPU (`nomodeset`) | tela preta ou travamento no `amdgpu` |
| Diagnóstico: console serial + tela (no UEFI, tecla **D** no menu) | logs completos (`loglevel=7`) |

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
./scripts/testar-uefi.sh ~/minivideo-build/ia-linux-minivideo.iso disco   # boot UEFI (OVMF)
```

Variante de CPU: `./scripts/build-iso.sh --variante ivybridge` (Xeon E5 **v2**
ou mais nova; liga F16C, RDRND e FSGSBASE; **não** roda no E5 v1).

- O Buildroot não oferece OpenBLAS para ivybridge, então essa variante fica
  sem ele.
- A padrão (corei7-avx) tem OpenBLAS e não tem F16C.
- Qual é mais rápida no seu E5-2630L v2: medir com
  `minivideo-modelos calibrar <gguf>` nas duas.
- Na CI: "Run workflow" → variante.

`scripts/validar-config.sh` compara cada linha do defconfig com o `.config`
final. Opção inexistente, oculta ou com dependência faltando vira erro, em
vez de sumir em silêncio.

Gravar no pendrive: `sudo dd if=ia-linux-minivideo.iso of=/dev/sdX bs=4M conv=fsync`
(confira `/dev/sdX` com `lsblk`; isso apaga o pendrive).

## Wi-Fi

Suporte embutido no kernel, com firmware:
- Intel (7260 até AX210);
- Qualcomm/Atheros (ath9k, ath10k);
- Realtek (rtw88 PCIe e USB, rtl8xxxu);
- MediaTek (MT7921/7922, MT7601U).

Para conectar: tecla **Q** → **[w]** (ou `minivideo-wifi redes` e
`minivideo-wifi conectar "SSID"` como root).

- A senha **não** é gravada: vai só a PSK derivada (PBKDF2, como o
  `wpa_passphrase`), em `Ferramentas/_rede/wifi.conf`, com permissão 600.
- No boot, o `S35wifi` reconecta sozinho.
- Redes que são só WPA3 (SAE) ainda não são suportadas.
- Sem teste em placa real.

## Diagnóstico para enviar

`minivideo-diagnostico --relatorio`, ou a tecla **D** e depois **R**, grava
`Logs/diagnostico-<data>.txt` e `.json`. Somente leitura, sem root. Inclui:
- modo de boot, instruções da CPU, placa/BIOS;
- `lspci`, `vulkaninfo`, `vainfo`, `aplay -l`, discos, rede, sensores da GPU;
- testes curtos: libx264, VA-API h264 sem B-frames, RIFE e Real-ESRGAN em
  Vulkan. Com `--completo`, também `llama-bench`.

É o primeiro passo na RX 580: copie os dois arquivos para um pendrive e envie.

## Release assinado

Criar a tag `minivideo-vX.Y.Z` faz a CI compilar as duas variantes e publicar
um GitHub Release com os dois ISOs, o `SHA256SUMS` e o `SHA256SUMS.sig`.
A tecla U mostra a versão nova. O **Enter** baixa o ISO da mesma variante para
`Saidas/` e só aceita o arquivo depois de conferir:
- a assinatura Ed25519 do `SHA256SUMS`;
- o sha256 do ISO.

Depois é só gravar com `dd`. O sistema em uso não muda.

Configurar a chave (uma vez, na sua máquina; a privada **nunca** vai para o
repositório):

```bash
openssl genpkey -algorithm ed25519 -out minivideo-assinatura.pem
openssl pkey -in minivideo-assinatura.pem -pubout \
    -out ia-linux-minivideo/image/rootfs-overlay/usr/share/minivideo/chave-publica.pem
git add ia-linux-minivideo/image/rootfs-overlay/usr/share/minivideo/chave-publica.pem
# GitHub → Settings → Secrets and variables → Actions → New repository secret:
#   nome MINIVIDEO_ASSINATURA_CHAVE, valor = conteúdo de minivideo-assinatura.pem
```

Sem a chave, o release sai só com `SHA256SUMS`, e a tecla U avisa e pede
confirmação.

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
| Assistente de prompts (C) e Atualizações (U) | diálogo, ficha, prompt por modelo, salvar; índice, sha256, troca atômica, reversão | pty + `pyte`; APIs e LLM simulados em servidor local (ver `ASSISTENTE_E_ATUALIZACOES.md`) |
| ISO completo: compilação + boot BIOS no QEMU + autoteste | **OK** | CI, run 36015350849 |
| Boot UEFI: kernel 6.18.52 com o fragmento (EFI + simpledrm) + `post-image.sh` + GRUB EFI | **OK** em OVMF como pendrive e como CD; BIOS continua OK (CD e pendrive); o ISO antigo falha em UEFI (`BdsDxe: failed to load`), como esperado | ISO de teste com initramfs mínimo (busybox), GRUB 2.12 do host; `scripts/testar-uefi.sh` |
| Boot UEFI do ISO completo (GRUB 2.14 do Buildroot) | **OK** como pendrive e como CD | CI, runs 36022545484 e 36030083147 |
| Squashfs + initramfs mínimo (`live-init`, `post-image.sh`) | **OK**: UEFI (CD e pendrive USB), BIOS (CD e pendrive USB), disco SATA, `toram` e falta do ISO (abre o shell de recuperação); raiz = overlay | kernel 6.18.52 recompilado com o fragmento; sistema de teste mínimo; QEMU/OVMF |
| Kernel com Wi-Fi + squashfs/overlay/iso9660/loop | todas as opções do fragmento aplicadas; `bzImage` compilado | árvore 6.18.52 real |
| Preparar disco MV_DADOS | lógica de proteção testada; preparo real num disco SATA virtual no autoteste da CI | `tests/test_disco.py`; CI |
| OpenBLAS no llama.cpp | erro da CI reproduzido (`sgemm_ not found` com OpenBLAS só CBLAS) e corrigido; build completo só na CI | CMake 3.28 com uma libopenblas só CBLAS |
| Download de modelos (M → B), ISO assinado, ETag, Wi-Fi (PSK), diagnóstico, limpeza de Jobs, quadros na RAM | testados | `pytest` (servidores locais; RIFE real com quadros em `/dev/shm`) |
| RX 580, VA-API, áudio, sensores, UEFI em placa real | **não testado** | pendente (hardware) |

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
| OpenBLAS com `TARGET=SANDYBRIDGE` acelera o llama.cpp na CPU AVX1 | **ativo** na variante padrão. A falha do run 35984047266 era do toolchain sem Fortran: o OpenBLAS sai só com CBLAS, sem o `sgemm_` que o FindBLAS testa. O `external.mk` corrige isso |
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
| **UEFI sem CSM** (placas novas) | GRUB EFI no mesmo ISO, kernel com stub EFI e simpledrm | teste em placa real; Secure Boot (ver abaixo) |
| **GPUs mistas** | cada GPU é um dispositivo independente; roteamento dGPU → APU → CUDA | escalonador por dispositivo com limite de memória |

## Avaliado e não feito nesta versão

- **Secure Boot.** Caminho viável:
  1. Usar o `shim` assinado pela Microsoft de uma distribuição.
  2. Assinar GRUB e kernel com uma chave própria (`sbsign`, com seção SBAT no GRUB).
  3. No primeiro boot, o usuário registra a chave no MokManager.

  Motivos para não fazer agora:
  - exige guardar mais uma chave privada na CI;
  - acrescenta um passo manual no primeiro boot;
  - placas X79 não têm Secure Boot.

  Para placas novas, basta desligá-lo no firmware. Dá para testar no QEMU
  com `OVMF_CODE_4M.secboot.fd` + `OVMF_VARS_4M.ms.fd` quando for implementado.
- **CUDA.** Exige:
  - um pacote próprio com os módulos abertos da NVIDIA
    (`open-gpu-kernel-modules`) e o espaço de usuário do driver, com vários GB;
  - PyTorch com CUDA num ambiente Python na partição de dados.

  Sem uma GPU NVIDIA para testar, qualquer pacote seria entregue sem
  validação. O ISO já está pronto do lado do sistema: `MODULES=y`, nouveau
  desligado, agentes e Safety Guard com classe `cuda`. Os prompts do
  assistente (tecla C) já saem no formato de Wan e LTX.
