# Integração com IA Linux Minimal — diagnóstico do boot e plano

Fonte analisada: branch `claude/dreamy-curie-j1yy53`, pasta
`ia-linux-minimal/` (último commit `cd7c721`, 2026-09-24). **Nada foi
alterado lá.** As correções abaixo são propostas para uma cópia separada.
Nada foi compilado nem inicializado nesta sessão (sem Buildroot, QEMU ou hardware).

## Estado herdado

Histórico de boot físico registrado no `CHANGELOG.md`:
1. GRUB não embutido no MBR → BIOS caía para PXE. Corrigido em `d9d2af1`.
2. GRUB passou a carregar, mas o kernel travava sem `/dev/sda`: faltavam
   `CONFIG_SCSI`/`CONFIG_BLK_DEV_SD`. Corrigido em `0eab4cd`, **nunca testado**.

## Problemas encontrados por leitura (não assumir resolvido)

### A. Bloqueante provável: `root=UUID=` sem initramfs
`buildroot/board/ia-linux/grub.cfg` passa ao kernel
`root=UUID=11111111-1111-4111-8111-111111111111` (UUID do **ext4**, gravado
por `tune2fs -U`). Não existe initramfs (nenhum `BR2_TARGET_ROOTFS_CPIO`,
`CONFIG_INITRAMFS_SOURCE` ou similar). Sem initramfs, o kernel só resolve
`root=` como `/dev/...`, `PARTUUID=`, `PARTLABEL=` ou `maj:min`. `UUID=`
de sistema de arquivos exige userspace (blkid). O `search --fs-uuid` do GRUB
funciona, mas só serve ao próprio GRUB.

Sintoma esperado depois da correção SCSI:
`VFS: Cannot open root device "UUID=..."` → `Kernel panic ... unknown-block(0,0)`.

Correção proposta (na cópia):
- BIOS/MBR: em `genimage-bios.cfg`, `hdimage { disk-signature = 0x1a11a001 }`.
  A partição `system` é a 1ª da tabela (boot/grub ficam fora dela), então
  `root=PARTUUID=1a11a001-01`. O `install-to-device.sh` grava com `dd`, e
  isso preserva a assinatura.
- UEFI/GPT: `partition-uuid = <uuid fixo>` na partição `system` de
  `genimage-uefi.cfg` e `root=PARTUUID=<esse uuid>`.
- Acrescentar **`rootwait`** às três entradas do GRUB: discos USB (e
  AHCI com probe assíncrono) aparecem depois da primeira tentativa de montagem.
- Manter o `search --fs-uuid` do GRUB como está.

### B. RX 580 sem firmware no boot: `CONFIG_DRM_AMDGPU=y`
O `amdgpu` está embutido no kernel, mas o firmware da Polaris
(`amdgpu/polaris10_*.bin`) vem do `BR2_PACKAGE_LINUX_FIRMWARE_AMDGPU` no rootfs,
que ainda não está montado quando o driver embutido sobe. Resultado provável:
`Direct firmware load ... failed with error -2`, sem `/dev/dri`, sem Vulkan
e sem sensores hwmon para o Safety Guard. Não trava o boot (a entrada
`nomodeset` continua útil).
Correção: `CONFIG_DRM_AMDGPU=m` (`CONFIG_MODULES=y` já existe) com
`modprobe amdgpu` no `rcS`, **ou** `CONFIG_EXTRA_FIRMWARE` listando os blobs
da Polaris 10/20.

### C. Faltas para o MiniVideo rodar dentro da imagem
- Áudio: nenhum `CONFIG_SND*` / ALSA → sem áudio.
- Rootfs sem FFmpeg, Python 3, vulkan-tools (existe), whisper.cpp, RIFE/Real-ESRGAN.
- Partição `system` com 2560 MiB. FFmpeg, Python e os binários NCNN
  precisam de revisão de tamanho. Pesos devem ir para a partição `data`.

## Ordem de integração (critérios de saída)

1. **Linux instalado atual:** rodar `minivideo-audit` e
   `minivideo-guard detect/watch` na RX 580. Instalar FFmpeg, vulkan-tools,
   whisper.cpp (compilado sem AVX2), RIFE e Real-ESRGAN NCNN. Testar o editor
   de verdade quando seu código estiver no repositório.
2. **Desacoplamento:** o núcleo do editor, os backends de IA, o Guard e a UI
   ficam em pacotes separados. O Guard já é independente (sem dependências).
3. **Cópia do IA Linux Minimal** (repositório ou branch próprio
   `ia-linux-minivideo-image`): aplicar A e B, validar com
   `scripts/validate-buildroot-configs.sh` e fazer boot em QEMU (virtio).
4. **Boot físico** SATA e USB no Xeon: montagem da raiz, ext4, `amdgpu` +
   firmware, `vulkaninfo`, áudio ALSA, entradas de recuperação.
5. Só então incluir FFmpeg, Python e o MiniVideo no rootfs e montar uma imagem de teste.

A imagem **não** deve ser anunciada como pronta antes dos passos 3 e 4 no hardware alvo.
