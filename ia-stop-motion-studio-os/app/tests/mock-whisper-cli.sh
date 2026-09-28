#!/usr/bin/env bash
# Fake whisper-cli for tests: writes <-of>.srt with two Portuguese lines.
while [ $# -gt 0 ]; do
    case "$1" in
        -of) out="$2"; shift 2 ;;
        -f) in="$2"; shift 2 ;;
        -l) lang="$2"; shift 2 ;;
        *) shift ;;
    esac
done
[ -s "$in" ] || { echo "sem entrada" >&2; exit 1; }
[ "$lang" = pt ] || { echo "idioma inesperado: $lang" >&2; exit 1; }
cat > "$out.srt" <<'SRT'
1
00:00:00,500 --> 00:00:01,500
Olá, eu sou o boneco!

2
00:00:02,000 --> 00:00:03,250
Vamos começar
o filme.
SRT
