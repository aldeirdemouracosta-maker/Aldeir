#!/bin/sh
# testar-uefi.sh <iso> [cd|disco] [log] — dá boot no ISO no QEMU com firmware
# UEFI (OVMF), escolhe a entrada "Diagnostico: console serial" do GRUB e
# confere pelo serial que o kernel subiu por EFI e que o sistema (squashfs) foi montado.
# "disco" simula o pendrive (o ISO gravado com dd).
# Requer: qemu-system-x86_64 e OVMF (Debian/Ubuntu: apt install qemu-system-x86 ovmf).
set -eu
ISO="$1"
MODO="${2:-disco}"
LOG="${3:-./uefi-${MODO}.log}"
CODE="${OVMF_CODE:-/usr/share/OVMF/OVMF_CODE_4M.fd}"
VARS_ORIG="${OVMF_VARS:-/usr/share/OVMF/OVMF_VARS_4M.fd}"
test -f "$ISO" && test -f "$CODE" && test -f "$VARS_ORIG"

TMP=$(mktemp -d)
trap 'kill "$QPID" 2>/dev/null || true; rm -rf "$TMP"' EXIT
cp "$VARS_ORIG" "$TMP/vars.fd"
: > "$LOG"
case "$MODO" in
    cd)    MIDIA="-cdrom $ISO" ;;
    # pendrive de verdade: disco USB (usb-storage num controlador xHCI)
    disco) MIDIA="-device qemu-xhci -drive file=$ISO,format=raw,if=none,id=pd,snapshot=on -device usb-storage,drive=pd" ;;
    *) echo "modo inválido: $MODO (cd|disco)" >&2; exit 2 ;;
esac
ACCEL=""; [ -w /dev/kvm ] && ACCEL="-enable-kvm"

# shellcheck disable=SC2086
qemu-system-x86_64 $ACCEL -m "${MEM:-2G}" -machine q35 -display none -no-reboot \
    -drive "if=pflash,format=raw,readonly=on,file=$CODE" \
    -drive "if=pflash,format=raw,file=$TMP/vars.fd" \
    $MIDIA -serial "file:$LOG" -monitor "unix:$TMP/mon,server,nowait" &
QPID=$!

espera() {  # espera <regex> <segundos>
    i=0
    while [ "$i" -lt "$2" ]; do
        grep -a -q -E "$1" "$LOG" && return 0
        kill -0 "$QPID" 2>/dev/null || return 1
        sleep 1; i=$((i + 1))
    done
    return 1
}
tecla() { printf 'sendkey %s\n' "$1" | python3 -c '
import socket, sys
s = socket.socket(socket.AF_UNIX); s.connect(sys.argv[1]); s.sendall(sys.stdin.buffer.read())' "$TMP/mon"; sleep 0.3; }

if ! espera "executed automatically" "${ESPERA_GRUB:-120}"; then
    echo "testar-uefi: menu do GRUB não apareceu (firmware não achou o BOOTX64.EFI?)" >&2
    exit 1
fi
# "Diagnostico" tem atalho --hotkey=d no grub-uefi.cfg: uma tecla só, sem navegar
# pelo menu com setas (na VM da CI uma seta às vezes se perdia e caía em outra entrada)
tecla d
# "minivideo-live: raiz" = o initramfs achou o ISO, montou o squashfs com overlay e fez switch_root
if espera "${MARCA_FINAL:-minivideo-live: raiz}" "${ESPERA_KERNEL:-300}" \
   && grep -a -q -E "efi: EFI v" "$LOG"; then
    echo "testar-uefi: OK ($MODO): GRUB EFI -> kernel (stub EFI) -> initramfs -> squashfs + overlay"
    exit 0
fi
echo "testar-uefi: kernel não chegou ao init por UEFI ($MODO); ver $LOG" >&2
exit 1
