#!/usr/bin/env bash
# Fake sd-cli for tests: prints a progress bar and writes a PNG of the requested size.
w=512; h=512; steps=4
while [ $# -gt 0 ]; do
    case "$1" in
        -o) out="$2"; shift 2 ;;
        -m) model="$2"; shift 2 ;;
        --width) w="$2"; shift 2 ;;
        --height) h="$2"; shift 2 ;;
        --steps) steps="$2"; shift 2 ;;
        *) shift ;;
    esac
done
[ -f "$model" ] || { echo "no model" >&2; exit 1; }
for i in $(seq 1 "$steps"); do printf '  |%s| %d/%d - 0.10s/it\r' "=====" "$i" "$steps"; done
echo
ffmpeg -v error -y -f lavfi -i "gradients=s=${w}x${h}" -frames:v 1 "$out"
