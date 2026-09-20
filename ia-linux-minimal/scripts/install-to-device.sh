#!/bin/sh
# install-to-device.sh <disk.img> </dev/sdX> <confirmação> — grava a
# imagem bootável do IA Linux Minimal (gerada por scripts/compile.sh,
# alvos bios/uefi) em um SSD/pendrive.
#
# DESTRUTIVO por natureza (é um `dd` para um dispositivo de bloco
# inteiro) — este script existe para tornar essa operação menos
# perigosa, não para escondê-la. As salvaguardas abaixo são
# best-effort, não uma garantia absoluta: confira o dispositivo de
# destino com cuidado antes de confirmar, sempre.
#
# A confirmação é o TERCEIRO argumento (o caminho do dispositivo
# repetido), não um prompt interativo. Em várias tentativas reais
# (ver CHANGELOG.md), `read` interativo voltava vazio de forma
# consistente e não diagnosticável em determinados ambientes de
# terminal, mesmo com /dev/tty, sem sudo, e com novas tentativas —
# então a confirmação não pode depender de um `read` no meio do
# script. Repetir o caminho na linha de comando preserva a mesma
# intenção de segurança (não existe atalho --yes; é preciso digitar o
# caminho do dispositivo de propósito) sem depender de leitura
# interativa de jeito nenhum.
#
# Roda no HOST (a máquina onde você grava o pendrive/SSD), não dentro
# do IA Linux Minimal.
set -eu

usage() {
    cat <<EOF
uso: $0 <caminho-para-disk.img> </dev/sdX> <confirmação>

A <confirmação> deve ser exatamente o mesmo caminho de </dev/sdX>,
repetido — é assim que este script confirma que você quer mesmo
gravar nesse dispositivo (não existe atalho --yes).

Exemplo:
  $0 disk.img /dev/sdd /dev/sdd

Salvaguardas aplicadas antes de gravar:
  - recusa se o destino não for um dispositivo de bloco de verdade
  - recusa se o destino parecer ser o disco onde a raiz (/) do host
    está montada (heurística via findmnt/lsblk — não é infalível)
  - recusa se a imagem for maior que o dispositivo
  - recusa se a confirmação não for exatamente igual ao caminho do
    dispositivo
EOF
}

IMG="${1:-}"
DEVICE="${2:-}"
CONFIRM="${3:-}"

if [ -z "${IMG}" ] || [ -z "${DEVICE}" ] || [ -z "${CONFIRM}" ]; then
    usage
    exit 1
fi

if [ "${CONFIRM}" != "${DEVICE}" ]; then
    echo "erro: a confirmação ('${CONFIRM}') não bate com o dispositivo ('${DEVICE}') — nada foi gravado" >&2
    exit 1
fi

if [ ! -f "${IMG}" ]; then
    echo "erro: imagem não encontrada: ${IMG}" >&2
    exit 1
fi

if [ ! -b "${DEVICE}" ]; then
    echo "erro: '${DEVICE}' não é um dispositivo de bloco" >&2
    exit 1
fi

# Heurística de segurança: recusa gravar sobre o dispositivo que contém
# a raiz do sistema atual (o host rodando este script), para reduzir o
# risco de um erro de digitação apagar a própria máquina.
#
# `lsblk -no PKNAME` só retorna algo quando a origem é uma PARTIÇÃO (dá
# o disco pai). Quando a raiz está montada direto num disco inteiro, sem
# partição (comum em VMs/containers — ex.: /dev/vda montado direto em
# / neste próprio ambiente de desenvolvimento), PKNAME vem vazio e a
# checagem original não pegava esse caso — por isso o fallback abaixo
# usa o nome base da própria origem quando PKNAME está vazio.
if command -v findmnt >/dev/null 2>&1 && command -v lsblk >/dev/null 2>&1; then
    ROOT_SOURCE="$(findmnt -n -o SOURCE / 2>/dev/null || true)"
    if [ -n "${ROOT_SOURCE}" ]; then
        ROOT_DEVICE_BASE="$(lsblk -no PKNAME "${ROOT_SOURCE}" 2>/dev/null || true)"
        if [ -z "${ROOT_DEVICE_BASE}" ]; then
            ROOT_DEVICE_BASE="$(basename "${ROOT_SOURCE}")"
        fi
        TARGET_BASE="$(basename "${DEVICE}")"
        if [ -n "${ROOT_DEVICE_BASE}" ] && [ "${TARGET_BASE}" = "${ROOT_DEVICE_BASE}" ]; then
            echo "erro: '${DEVICE}' parece ser o disco onde este sistema (host) está instalado — recusando" >&2
            exit 1
        fi
    else
        echo "aviso: não foi possível determinar o disco raiz do host (findmnt sem saída) — a checagem de segurança 'não é o disco do host' NÃO rodou para esta gravação" >&2
    fi
else
    echo "aviso: findmnt e/ou lsblk não encontrados — a checagem de segurança 'não é o disco do host' NÃO rodou para esta gravação" >&2
fi

IMG_SIZE="$(stat -c %s "${IMG}" 2>/dev/null || stat -f %z "${IMG}" 2>/dev/null || echo 0)"
DEVICE_SIZE="$(blockdev --getsize64 "${DEVICE}" 2>/dev/null || echo 0)"

if [ "${DEVICE_SIZE}" -gt 0 ] && [ "${IMG_SIZE}" -gt "${DEVICE_SIZE}" ]; then
    echo "erro: a imagem (${IMG_SIZE} bytes) é maior que o dispositivo (${DEVICE_SIZE} bytes)" >&2
    exit 1
fi

echo "Imagem : ${IMG} ($((IMG_SIZE / 1024 / 1024)) MiB)"
echo "Destino: ${DEVICE} ($((DEVICE_SIZE / 1024 / 1024)) MiB)"
echo "Confirmação recebida: ${CONFIRM} (bate com o destino)"
echo
echo "ATENÇÃO: isto apaga TUDO em ${DEVICE}. Não há como desfazer."
echo "gravando ${IMG} em ${DEVICE}..."
dd if="${IMG}" of="${DEVICE}" bs=4M status=progress conv=fsync
sync

echo "concluído. ${DEVICE} pode ser removido com segurança."
