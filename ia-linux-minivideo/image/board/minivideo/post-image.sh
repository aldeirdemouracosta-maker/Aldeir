#!/bin/sh
# Acrescenta boot UEFI ao ISO híbrido isolinux gerado pelo Buildroot.
#
# O Buildroot só gera ISO híbrido (gravável em pendrive) com isolinux, que é
# BIOS/legado. Aqui o ISO é refeito com o mesmo conteúdo e duas entradas El
# Torito: isolinux (BIOS) e uma imagem FAT com o GRUB EFI (UEFI). Com
# -isohybrid-gpt-basdat, a imagem FAT também vira partição EFI no pendrive.
# Resultado: um único arquivo que dá boot em BIOS e UEFI, em CD e em pendrive.
#
# Com rootfs.squashfs presente, o sistema também vai para o ISO como
# live/rootfs.squashfs e /boot/initrd vira um initramfs mínimo (busybox,
# firmware e live-init) que monta o squashfs com overlay e faz switch_root.
#
# Chamado pelo Buildroot como BR2_ROOTFS_POST_IMAGE_SCRIPT, com BINARIES_DIR,
# TARGET_DIR e HOST_DIR no ambiente. Também roda fora do Buildroot (teste local): nesse
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
# boot.cat é recriado; efiboot.img e live/ também (o script pode rodar de novo sobre um ISO já processado)
rm -rf "$T/isolinux/boot.cat" "$T/boot.catalog" "$T/boot/efiboot.img" "$T/live"
for f in isolinux/isolinux.bin boot/bzImage boot/initrd; do
	[ -f "$T/$f" ] || { echo "post-image: falta $f no ISO" >&2; exit 1; }
done

# ---- sistema em squashfs + initramfs mínimo ----
SQ="$BINARIES_DIR/rootfs.squashfs"
if [ -f "$SQ" ]; then
    TARGET_DIR=${TARGET_DIR:?TARGET_DIR não definido}
    READELF=$(ls "${HOST_DIR:-/nonexistent}"/bin/*-linux-gnu-readelf 2>/dev/null | head -1)
    READELF=${READELF:-readelf}
    M="$BINARIES_DIR/initrd-live"
    rm -rf "$M"
    mkdir -p "$M/bin" "$M/dev" "$M/proc" "$M/sys" "$M/lib" "$M/newroot" \
             "$M/mnt/iso" "$M/mnt/sq" "$M/mnt/rw" "$M/mnt/ram"
    ln -s lib "$M/lib64"
    cp -L "$TARGET_DIR/bin/busybox" "$M/bin/busybox"
    # bibliotecas do busybox (glibc), resolvidas pelo DT_NEEDED de forma recursiva
    fila="$M/bin/busybox"
    interp=$("$READELF" -l "$M/bin/busybox" 2>/dev/null | sed -n 's/.*program interpreter: \(.*\)\]/\1/p')
    [ -n "$interp" ] && cp -L "$TARGET_DIR$interp" "$M/lib/$(basename "$interp")"
    while [ -n "$fila" ]; do
        prox=""
        for f in $fila; do
            for lib in $("$READELF" -d "$f" 2>/dev/null | sed -n 's/.*(NEEDED).*\[\(.*\)\]/\1/p'); do
                [ -e "$M/lib/$lib" ] && continue
                src=$(ls "$TARGET_DIR/lib/$lib" "$TARGET_DIR/usr/lib/$lib" "$TARGET_DIR/lib64/$lib" 2>/dev/null | head -1)
                [ -n "$src" ] || { echo "post-image: biblioteca $lib não encontrada" >&2; exit 1; }
                cp -L "$src" "$M/lib/$lib"
                prox="$prox $M/lib/$lib"
            done
        done
        fila="$prox"
    done
    # firmware no initramfs: drivers embutidos (amdgpu, Wi-Fi, rede) carregam no boot;
    # é liberado da RAM no switch_root
    [ -d "$TARGET_DIR/lib/firmware" ] && cp -a "$TARGET_DIR/lib/firmware" "$M/lib/"
    install -m 0755 "$BOARD_DIR/live-init" "$M/init"
    ( cd "$M" && find . | LC_ALL=C sort | cpio -o -H newc -R 0:0 --quiet ) | gzip -9 > "$BINARIES_DIR/initrd-live.img"
    rm -rf "$M"
fi

# MBR isohybrid (isohdpfx) que o isohybrid do Buildroot gravou: 432 bytes de
# código; a tabela de partições é refeita pelo xorriso.
dd if="$ISO" of="$BINARIES_DIR/mbr-isohybrid.bin" bs=432 count=1 2>/dev/null

# GRUB EFI: o menu fica no ISO; a marca permite ao GRUB achar o ISO9660.
install -D -m 0644 "$BOARD_DIR/grub-uefi.cfg" "$T/boot/grub/grub.cfg"
echo "IA-Linux MiniVideo" > "$T/boot/minivideo-uefi.id"
install -D -m 0644 "$EFI" "$T/EFI/BOOT/BOOTX64.EFI"
if [ -f "$SQ" ]; then
    install -D -m 0644 "$SQ" "$T/live/rootfs.squashfs"
    install -m 0644 "$BINARIES_DIR/initrd-live.img" "$T/boot/initrd"
fi

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
