#!/usr/bin/env bash
# Constrói a ISO do IA Stop-Motion Studio OS (Ubuntu 24.04 + kernel HWE,
# boot direto no estúdio em tela cheia, sessão live com opção de persistência).
#
#   sudo ./iso/construir-iso.sh
#
# Variáveis:
#   FERRAMENTAS="rhubarb realesrgan ia voz cenarios scx"   ferramentas embutidas
#                                    (padrão: rhubarb realesrgan scx; "ia", "voz" e
#                                    "cenarios" baixam modelos grandes)
#   MIRROR=http://archive.ubuntu.com/ubuntu   espelho do Ubuntu
#   TRABALHO=/var/tmp/ia-sms-iso              pasta de trabalho (~8 GB livres)
#   SAIDA=iso/saida                           onde a ISO é gravada
#
# Requer (host Ubuntu/Debian): debootstrap squashfs-tools xorriso grub-pc-bin
# grub-efi-amd64-bin mtools dosfstools, e para "scx": clang libelf-dev zlib1g-dev.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
VERSION="$(sed -n 's/^project(ia-stop-motion-studio-os VERSION \([0-9.]*\).*/\1/p' "$REPO/app/CMakeLists.txt")"
DIST=noble
MIRROR="${MIRROR:-http://archive.ubuntu.com/ubuntu}"
WORK="${TRABALHO:-/var/tmp/ia-sms-iso}"
OUT="${SAIDA:-$HERE/saida}"
TOOLS="${FERRAMENTAS:-rhubarb realesrgan scx}"
CHROOT="$WORK/chroot"
ISOROOT="$WORK/iso"
ISO="$OUT/ia-stop-motion-studio-os-${VERSION}-amd64.iso"

[ "$(id -u)" -eq 0 ] || { echo "rode com sudo" >&2; exit 1; }
log() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
want() { [[ " $TOOLS " == *" $1 "* ]]; }

mounts=()
cleanup() {
    for ((i = ${#mounts[@]} - 1; i >= 0; i--)); do umount -lf "${mounts[$i]}" 2>/dev/null || true; done
}
trap cleanup EXIT
bind() { mount --bind "$1" "$2"; mounts+=("$2"); }
in_chroot() { chroot "$CHROOT" /usr/bin/env -i HOME=/root PATH=/usr/sbin:/usr/bin:/sbin:/bin \
    DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8 "$@"; }

# ── 1. sistema base ────────────────────────────────────────────────────
if [ ! -x "$CHROOT/usr/bin/apt-get" ]; then
    log "debootstrap $DIST"
    mkdir -p "$WORK"
    debootstrap --arch=amd64 --variant=minbase --components=main,restricted,universe,multiverse \
        "$DIST" "$CHROOT" "$MIRROR"
fi
bind /dev "$CHROOT/dev"
bind /dev/pts "$CHROOT/dev/pts"
mount -t proc proc "$CHROOT/proc"; mounts+=("$CHROOT/proc")
mount -t sysfs sysfs "$CHROOT/sys"; mounts+=("$CHROOT/sys")
cp /etc/resolv.conf "$CHROOT/etc/resolv.conf"
cat > "$CHROOT/etc/apt/sources.list" <<SRC
deb $MIRROR $DIST main restricted universe multiverse
deb $MIRROR $DIST-updates main restricted universe multiverse
deb $MIRROR $DIST-security main restricted universe multiverse
SRC
# Nada de daemons iniciando dentro do chroot.
printf '#!/bin/sh\nexit 101\n' > "$CHROOT/usr/sbin/policy-rc.d"; chmod +x "$CHROOT/usr/sbin/policy-rc.d"

log "pacotes do sistema"
in_chroot apt-get update -q
in_chroot apt-get install -y -q --no-install-recommends \
    linux-image-generic-hwe-24.04 linux-firmware casper initramfs-tools systemd-sysv dbus-broker \
    sudo locales tzdata keyboard-configuration console-setup kbd \
    network-manager wpasupplicant iproute2 ca-certificates curl \
    pipewire pipewire-pulse wireplumber alsa-utils \
    mesa-vulkan-drivers libgl1-mesa-dri libegl-mesa0 mesa-va-drivers vulkan-tools \
    cage foot fonts-dejavu fonts-noto-color-emoji xdg-user-dirs \
    qt6-wayland libqt6multimedia6 libqt6concurrent6 libqt6svg6 qml6-module-qtqml-models \
    qml6-module-qtquick qml6-module-qtquick-controls qml6-module-qtquick-layouts \
    qml6-module-qtquick-window qml6-module-qtquick-dialogs qml6-module-qtmultimedia \
    qml6-module-qtqml-workerscript qml6-module-qtquick-templates qml6-module-qtcore qt6-image-formats-plugins \
    gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-libav \
    ffmpeg melt gphoto2 v4l-utils polkitd pkexec python3 python3-venv libelf1t64 zlib1g \
    unzip git

log "pt-BR, fuso e teclado ABNT2"
sed -i 's/^# *pt_BR.UTF-8/pt_BR.UTF-8/' "$CHROOT/etc/locale.gen"
in_chroot locale-gen
echo 'LANG=pt_BR.UTF-8' > "$CHROOT/etc/default/locale"
ln -sf /usr/share/zoneinfo/America/Sao_Paulo "$CHROOT/etc/localtime"
cat > "$CHROOT/etc/default/keyboard" <<KB
XKBMODEL="abnt2"
XKBLAYOUT="br"
XKBVARIANT=""
XKBOPTIONS=""
KB
echo ia-stop-motion > "$CHROOT/etc/hostname"

# ── 2. o estúdio ───────────────────────────────────────────────────────
log "compilando o IA Stop-Motion Studio OS dentro do sistema"
BUILD_DEPS="cmake g++ make qt6-base-dev qt6-declarative-dev qt6-multimedia-dev libgl-dev"
in_chroot apt-get install -y -q --no-install-recommends $BUILD_DEPS
rm -rf "${CHROOT:?}/tmp/app"
cp -r "$REPO/app" "$CHROOT/tmp/app"
in_chroot cmake -S /tmp/app -B /tmp/app/build -DCMAKE_BUILD_TYPE=Release
in_chroot cmake --build /tmp/app/build --target ia-stop-motion-studio -j"$(nproc)"
install -m755 "$CHROOT/tmp/app/build/ia-stop-motion-studio" "$CHROOT/usr/local/bin/ia-stop-motion-studio"
rm -rf "${CHROOT:?}/tmp/app"
in_chroot apt-get purge -y -q $BUILD_DEPS
in_chroot apt-get autoremove -y -q --purge

log "modos do sistema e ferramentas: $TOOLS"
DESTDIR="$CHROOT" "$REPO/scripts/instalar-modos.sh"
install -Dm755 "$REPO/system/ia-sms-ia.py" "$CHROOT/opt/ia-stop-motion/ferramentas/ia-sms-ia.py"
if want scx; then
    DESTDIR="$CHROOT" "$REPO/scripts/instalar-scx-studio.sh"
    in_chroot systemctl enable scx-studio.service
fi
# Ferramentas de usuário vão para /opt; cada usuário as vê em ~/IA-StopMotion/ferramentas.
for t in rhubarb realesrgan ia voz cenarios; do
    want "$t" || continue
    case "$t" in
        ia) script=instalar-ia.sh ;; voz) script=instalar-voz.sh ;; cenarios) script=instalar-cenarios.sh ;;
        *) script="instalar-$t.sh" ;;
    esac
    IA_SMS_HOME="$CHROOT/opt/ia-stop-motion" "$REPO/scripts/$script"
done
# O venv do Python guarda caminhos absolutos: recria dentro do sistema.
if want ia; then
    rm -rf "${CHROOT:?}/opt/ia-stop-motion/ferramentas/ia-python"
    in_chroot python3 -m venv /opt/ia-stop-motion/ferramentas/ia-python
    in_chroot /opt/ia-stop-motion/ferramentas/ia-python/bin/pip install -q onnxruntime numpy pillow
fi
mkdir -p "$CHROOT/etc/skel/IA-StopMotion"
ln -sfn /opt/ia-stop-motion/ferramentas "$CHROOT/etc/skel/IA-StopMotion/ferramentas"

log "sessão do estúdio"
install -Dm755 "$HERE/arquivos/ia-sms-sessao" "$CHROOT/usr/local/bin/ia-sms-sessao"
install -Dm644 "$HERE/arquivos/bash_profile" "$CHROOT/etc/skel/.bash_profile"
install -Dm644 "$HERE/arquivos/autologin.conf" "$CHROOT/etc/systemd/system/getty@tty1.service.d/autologin.conf"
install -Dm644 "$HERE/arquivos/ia-sms-grupos.service" "$CHROOT/etc/systemd/system/ia-sms-grupos.service"
install -Dm644 "$HERE/arquivos/casper.conf" "$CHROOT/etc/casper.conf"
install -Dm755 "$HERE/arquivos/ia-sms-diagnostico" "$CHROOT/usr/local/bin/ia-sms-diagnostico"
install -Dm644 "$HERE/arquivos/ia-sms-diagnostico.service" "$CHROOT/etc/systemd/system/ia-sms-diagnostico.service"
sed "s/@VERSAO@/$VERSION/" "$HERE/arquivos/os-release-extra" > "$CHROOT/etc/ia-stop-motion-release"
in_chroot systemctl enable ia-sms-grupos.service ia-sms-diagnostico.service NetworkManager.service

rm -f "${CHROOT:?}/usr/sbin/policy-rc.d" "${CHROOT:?}/etc/resolv.conf"
in_chroot apt-get clean
find "${CHROOT:?}/var/lib/apt/lists" "${CHROOT:?}/tmp" -mindepth 1 -delete
in_chroot update-initramfs -u -k all

# ── 3. imagem live ──────────────────────────────────────────────────────
log "squashfs"
cleanup; mounts=()
[ -d "$ISOROOT" ] && find "${ISOROOT:?}" -mindepth 1 -delete
mkdir -p "$ISOROOT/casper" "$ISOROOT/boot/grub" "$ISOROOT/.disk"
cp "$(ls -1 "$CHROOT"/boot/vmlinuz-* | sort -V | tail -1)" "$ISOROOT/casper/vmlinuz"
cp "$(ls -1 "$CHROOT"/boot/initrd.img-* | sort -V | tail -1)" "$ISOROOT/casper/initrd"
mksquashfs "$CHROOT" "$ISOROOT/casper/filesystem.squashfs" -noappend -comp zstd -Xcompression-level 15 \
    -wildcards -e 'boot/vmlinuz*' -e 'boot/initrd.img*'
du -sx --block-size=1 "$CHROOT" | cut -f1 > "$ISOROOT/casper/filesystem.size"
echo "IA Stop-Motion Studio OS $VERSION amd64" > "$ISOROOT/.disk/info"
sed "s/@VERSAO@/$VERSION/" "$HERE/arquivos/grub.cfg" > "$ISOROOT/boot/grub/grub.cfg"

log "ISO (BIOS + UEFI)"
mkdir -p "$OUT"
grub-mkrescue -o "$ISO" "$ISOROOT" -- -volid "IA_SMS_OS" 2>&1 | grep -v "^xorriso : UPDATE" || true
sha256sum "$ISO" > "$ISO.sha256"
log "pronto: $ISO ($(du -h "$ISO" | cut -f1))"
