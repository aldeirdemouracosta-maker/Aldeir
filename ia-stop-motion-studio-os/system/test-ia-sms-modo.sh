#!/usr/bin/env bash
# Testa ia-sms-modo contra uma árvore sysfs falsa (RX 580 + 2 CPUs).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
fail() { echo "FALHOU: $*" >&2; exit 1; }

make_tree() {
    local t; t="$(mktemp -d)"
    mkdir -p "$t/class/drm/card0/device" "$t/class/drm/card1" # card1: sem amdgpu
    echo auto > "$t/class/drm/card0/device/power_dpm_force_performance_level"
    cat > "$t/class/drm/card0/device/pp_power_profile_mode" <<'TABLE'
NUM        MODE_NAME     SCLK_UP_HYST   SCLK_DOWN_HYST SCLK_ACTIVE_LEVEL     MCLK_UP_HYST   MCLK_DOWN_HYST MCLK_ACTIVE_LEVEL
  0   BOOTUP_DEFAULT:        -              -              -              -              -              -
  1 3D_FULL_SCREEN *:        0            100             30              0            100             10
  2     POWER_SAVING:       10              0             30              -              -              -
  3            VIDEO:        -              -              -             10             16             31
  4               VR:        0             11             50              0            100             10
  5          COMPUTE:        0              5             30              -              -              -
  6           CUSTOM:        -              -              -              -              -              -
TABLE
    for c in 0 1; do
        mkdir -p "$t/devices/system/cpu/cpu$c/cpufreq"
        echo schedutil > "$t/devices/system/cpu/cpu$c/cpufreq/scaling_governor"
        echo "performance schedutil powersave" > "$t/devices/system/cpu/cpu$c/cpufreq/scaling_available_governors"
    done
    echo "$t"
}
run() { IA_SMS_SYSFS="$1" IA_SMS_STATE_DIR="$1/run" "$HERE/ia-sms-modo" "${@:2}" >/dev/null || fail "ia-sms-modo ${*:2} saiu com erro"; }

t=$(make_tree); run "$t" ia
[ "$(cat "$t/class/drm/card0/device/power_dpm_force_performance_level")" = manual ] || fail "ia: nível"
[ "$(cat "$t/class/drm/card0/device/pp_power_profile_mode")" = 5 ] || fail "ia: perfil COMPUTE"
[ "$(cat "$t/devices/system/cpu/cpu1/cpufreq/scaling_governor")" = performance ] || fail "ia: governor"
[ "$(cat "$t/run/modo")" = ia ] || fail "ia: estado"

t=$(make_tree); run "$t" render
[ "$(cat "$t/class/drm/card0/device/pp_power_profile_mode")" = 3 ] || fail "render: perfil VIDEO"

t=$(make_tree); run "$t" ia; run "$t" captura
[ "$(cat "$t/class/drm/card0/device/power_dpm_force_performance_level")" = auto ] || fail "captura: nível"
[ "$(cat "$t/devices/system/cpu/cpu0/cpufreq/scaling_governor")" = schedutil ] || fail "captura: governor"

# Sem tabela de perfis (GPU que não suporta): cai para "high".
t=$(make_tree); rm "$t/class/drm/card0/device/pp_power_profile_mode"; run "$t" render
[ "$(cat "$t/class/drm/card0/device/power_dpm_force_performance_level")" = high ] || fail "render sem perfis"

# Entradas inválidas são recusadas.
if IA_SMS_SYSFS="$t" "$HERE/ia-sms-modo" "rm -rf" 2>/dev/null; then fail "aceitou modo inválido"; fi
if IA_SMS_SYSFS="$t" "$HERE/ia-sms-modo" ia --pid "1;x" 2>/dev/null; then fail "aceitou PID inválido"; fi
# scx_studio: com os mapas fixados, grava o modo e registra o app (UI) e
# seus filhos (workers) — bpftool falso registra as chamadas.
t=$(make_tree); mkdir -p "$t/bpf"; touch "$t/bpf/cfg" "$t/bpf/tasks"
cat > "$t/bpftool" <<'MOCK'
#!/bin/sh
echo "$@" >> "$(dirname "$0")/bpftool.log"
MOCK
chmod +x "$t/bpftool"
sleep 5 & child=$!
IA_SMS_SYSFS="$t" IA_SMS_STATE_DIR="$t/run" IA_SMS_BPFFS="$t/bpf" IA_SMS_BPFTOOL="$t/bpftool" \
    "$HERE/ia-sms-modo" ia --pid $$ >/dev/null || fail "scx_studio: saiu com erro"
kill $child 2>/dev/null || true
grep -q "map update pinned $t/bpf/cfg key 0 0 0 0 value 3 0 0 0 0 0 0 0" "$t/bpftool.log" || fail "scx_studio: modo"
pid=$$
grep -q "map update pinned $t/bpf/tasks key $((pid & 255)) $(((pid >> 8) & 255)) $(((pid >> 16) & 255)) 0 value 1 0 0 0" "$t/bpftool.log" || fail "scx_studio: UI"
grep -q "map update pinned $t/bpf/tasks key $((child & 255)) $(((child >> 8) & 255)) $(((child >> 16) & 255)) 0 value 2 0 0 0" "$t/bpftool.log" || fail "scx_studio: worker"

echo "ia-sms-modo: todos os testes passaram"
