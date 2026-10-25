# Build reproduzível da primeira ISO

**Status: plano. Nenhuma ISO foi compilada ou testada.** Não declare a existência da ISO antes dos gates abaixo.

## Requisitos do host de build
Debian ou Ubuntu (VM, WSL2 com systemd, ou container privilegiado), ~15 GB livres. Dentro de **um host de build**, não no seu
sistema principal, instalar: `live-build`, `xorriso`, `squashfs-tools`, `qemu-system-x86`, `ovmf`, `isolinux`, `syslinux-utils`.
(Em WSL2 pode falhar por loop/chroot — preferir VM Debian. Instalação é decisão sua; este plano não a executa.)

## Passos
1. `git clone` do projeto; `scripts/build-iso.sh --confirmo-build` gera `build-iso/` com `lb config` (opções a validar com
   `lb config --help` da versão instalada).
2. Listas de pacotes mínimas em `config/package-lists/rea.list.chroot`: `xorg` (mínimo), `fluxbox`, `python3-gi`,
   `gir1.2-gtk-3.0`, `xterm` ou terminal leve, `p7zip-full`, `file`, `xxd`, `jq`. Sem *recommends*. Sem firmware não-livre no
   início (pode afetar Wi-Fi/GPU: registrar como limitação).
3. `sudo lb build` → `live-image-amd64.hybrid.iso`.
4. Pins: fixar snapshot do repositório Debian (snapshot.debian.org) e a versão do live-build no log para reprodutibilidade;
   registrar `SHA256SUMS` da ISO e a lista de pacotes (`*.packages`).

## Gate G1 — critérios de aceite (todos devem passar e ser registrados)
| # | Teste | Comando-base | Aprovado se |
|---|---|---|---|
| 1 | Tamanho | `ls -l *.iso` | ≤ 700 MB (senão: spike Alpine, ver ARQUITETURA-OS) |
| 2 | Boot BIOS | `qemu-system-x86_64 -m 2048 -cdrom X.iso -boot d` | chega ao Fluxbox |
| 3 | Boot UEFI | idem + `-bios /usr/share/OVMF/OVMF_CODE_4M.fd` (caminho varia) | chega ao Fluxbox |
| 4 | Sem AVX2 | `-cpu Nehalem` | boot e shell abrem |
| 5 | Offline | QEMU `-nic none` | tudo do núcleo funciona |
| 6 | Disco intocado | disco virtual com tabela de partições; hash dos 1 MiB iniciais antes/depois | idêntico |
| 7 | Memória | `free -m` ocioso na VM de 2 GB | registrar; meta shell < 150 MB |
| 8 | Hardware real | pendrive (gravado com ferramenta de sua escolha) em ao menos um PC BIOS e um UEFI | boot OK — **só então** afirmar suporte |

Cada execução gera relatório em `relatorios/` com data, hash da ISO e saídas. Falha em qualquer item = ISO não liberada.
