#!/bin/sh
# Acrescenta boot UEFI ao ISO híbrido isolinux gerado pelo Buildroot.
#
# O Buildroot só gera ISO híbrido (gravável em pendrive) com isolinux, que é
# BIOS/legado. Aqui o ISO é refeito com o mesmo conteúdo e duas entradas El
# Torito: isolinux (BIOS) e uma imagem FAT com o GRUB EFI (UEFI). Com
# -isohybrid-gpt-basdat, a imagem FAT também vira partição EFI no pendrive.
# Resultado: um único arquivo que dá boot em BIOS e UEFI, em CD e em pendrive.
#
# Chamado pelo Buildroot como BR2_ROOTFS_POST_IMAGE_SCRIPT, com BINARIES_DIR e
# HOST_DIR no ambiente. Também roda fora do Buildroot (teste local): nesse
# caso XORRISO/MKFS_FAT/MMD/MCOPY podem apontar para as ferramentas do host.
set -eu

BINARIES_DIR=${BINARIES_DIR:?BINARIES_DIR não definido}
BOARD_DIR=$(dirname "$0")
if [ -n "${HOST_DIR:-}" ]; then
	XORRISO=${XORRISO:-$HOST_DIR/bin/xorriso}
	MKFS_FAT=${MKFS_FAT:-$HOST_DIR/sbin/mkfs.fat}
	MMD=${MMD:-$HOST_DIR/bin/mmd}
	MCOPY=${MCOPY:-$HOST_DIR/bin/mcopy}
fi
XORRISO=${XORRISO:-xorriso}
MKFS_FAT=${MKFS_FAT:-mkfs.fat}
MMD=${MMD:-mmd}
MCOPY=${MCOPY:-mcopy}

ISO=$BINARIES_DIR/rootfs.iso9660
EFI=$BINARIES_DIR/efi-part/EFI/BOOT/bootx64.efi
[ -f "$ISO" ] || { echo "post-image: $ISO não existe" >&2; exit 1; }
[ -f "$EFI" ] || { echo "post-image: $EFI não existe (BR2_TARGET_GRUB2_X86_64_EFI)" >&2; exit 1; }

T=$BINARIES_DIR/iso-uefi
rm -rf "$T" "$BINARIES_DIR/efiboot.img" "$BINARIES_DIR/mbr-isohybrid.bin"
mkdir -p "$T"

# Conteúdo atual do ISO (isolinux, kernel, initrd)
"$XORRISO" -osirrox on -indev "$ISO" -extract / "$T" >/dev/null 2>&1
chmod -R u+w "$T"
# boot.cat é recriado pelo xorriso
rm -f "$T/isolinux/boot.cat"
for f in isolinux/isolinux.bin boot/bzImage boot/initrd; do
	[ -f "$T/$f" ] || { echo "post-image: falta $f no ISO" >&2; exit 1; }
done

# MBR isohybrid (isohdpfx) que o isohybrid do Buildroot gravou: 432 bytes de
# código; a tabela de partições é refeita pelo xorriso.
dd if="$ISO" of="$BINARIES_DIR/mbr-isohybrid.bin" bs=432 count=1 2>/dev/null

# GRUB EFI: o menu fica no ISO; a marca permite ao GRUB achar o ISO9660.
install -D -m 0644 "$BOARD_DIR/grub-uefi.cfg" "$T/boot/grub/grub.cfg"
echo "IA-Linux MiniVideo" > "$T/boot/minivideo-uefi.id"
install -D -m 0644 "$EFI" "$T/EFI/BOOT/BOOTX64.EFI"

# Imagem FAT da entrada El Torito UEFI (também é a partição EFI no pendrive)
IMG=$T/boot/efiboot.img
kib=$(( ($(stat -c %s "$EFI") / 1024) + 512 ))
"$MKFS_FAT" -C -n MV_EFI "$IMG" "$kib" >/dev/null
"$MMD" -i "$IMG" ::/EFI ::/EFI/BOOT
"$MCOPY" -i "$IMG" "$EFI" ::/EFI/BOOT/BOOTX64.EFI

OUT=$BINARIES_DIR/rootfs-uefi.iso9660
"$XORRISO" -as mkisofs -iso-level 3 -J -R -V MINIVIDEO \
	-b isolinux/isolinux.bin -c isolinux/boot.cat \
	-no-emul-boot -boot-load-size 4 -boot-info-table \
	-isohybrid-mbr "$BINARIES_DIR/mbr-isohybrid.bin" \
	-eltorito-alt-boot -e boot/efiboot.img -no-emul-boot \
	-isohybrid-gpt-basdat \
	-o "$OUT" "$T"

mv "$OUT" "$ISO"
rm -rf "$T" "$BINARIES_DIR/mbr-isohybrid.bin"
echo "post-image: ISO com boot BIOS (isolinux) + UEFI (GRUB): $ISO"
