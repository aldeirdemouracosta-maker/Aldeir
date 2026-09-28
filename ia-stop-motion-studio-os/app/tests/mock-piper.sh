#!/usr/bin/env bash
# Fake piper for tests: reads text on stdin, writes a WAV whose length grows with it.
while [ $# -gt 0 ]; do
    case "$1" in
        --output_file) out="$2"; shift 2 ;;
        --model) model="$2"; shift 2 ;;
        *) shift ;;
    esac
done
[ -f "$model" ] || { echo "modelo ausente" >&2; exit 1; }
text="$(cat)"
secs=$(( ${#text} / 12 + 1 ))
ffmpeg -v error -y -f lavfi -i "sine=f=200:d=$secs" "$out"
