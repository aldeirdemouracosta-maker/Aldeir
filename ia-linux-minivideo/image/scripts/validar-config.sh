#!/bin/sh
# validar-config.sh <.config> <defconfig> — confere se cada opção pedida no
# defconfig sobreviveu ao Kconfig do Buildroot. Símbolo oculto, inexistente
# ou com dependência faltando some em silêncio no "make defconfig"; aqui vira erro.
set -eu
CONFIG="$1"
DEFCONFIG="$2"
fail=0
while IFS= read -r line; do
    case "$line" in
        BR2_*=*)
            key=${line%%=*}
            want=${line#*=}
            got=$(grep -E "^${key}=" "$CONFIG" | head -1 | cut -d= -f2- || true)
            if [ "$got" != "$want" ]; then
                echo "DIVERGE: ${key} pedido=${want} obtido=${got:-não definido}"
                fail=1
            fi
            ;;
    esac
done < "$DEFCONFIG"
if [ "$fail" -ne 0 ]; then
    echo "validar-config: há opções descartadas pelo Kconfig (ver acima)" >&2
    exit 1
fi
echo "validar-config: todas as opções do defconfig estão ativas em ${CONFIG}"
