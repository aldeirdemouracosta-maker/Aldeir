#!/usr/bin/env bash
# Fake gphoto2 for tests: one "Canon EOS 1100D", live view streams the JPEG in
# $MOCK_GPHOTO2_JPEG a few times, capture downloads it.
args=("$@")
has() { for a in "${args[@]}"; do [ "$a" = "$1" ] && return 0; done; return 1; }

if has --auto-detect; then
    printf 'Model                          Port            \n'
    printf -- '----------------------------------------------------------\n'
    printf 'Canon EOS 1100D                usb:001,004     \n'
    exit 0
fi
if has --capture-movie; then
    for i in 1 2 3 4 5; do cat "$MOCK_GPHOTO2_JPEG"; sleep 0.05; done
    exec sleep 30
fi
if has --capture-image-and-download; then
    for ((i = 0; i < ${#args[@]}; i++)); do
        [ "${args[$i]}" = "--filename" ] && name="${args[$((i + 1))]}"
    done
    cp "$MOCK_GPHOTO2_JPEG" "${name//%C/jpg}"
    echo "Saving file as ${name//%C/jpg}"
    exit 0
fi
echo "unsupported: $*" >&2
exit 1
