#!/bin/sh
# Validação da Fase 0: formatação, vet, testes e compilação. Não altera o sistema.
set -u
cd "$(dirname "$0")/.." || exit 1
fail=0
echo "== gofmt";   out=$(gofmt -l .); [ -z "$out" ] && echo ok || { echo "$out"; fail=1; }
echo "== go vet";  go vet ./...            || fail=1
echo "== go test"; go test ./... -count=1  || fail=1
echo "== build";   go build -o bin/hrail ./cmd/hrail && echo "bin/hrail compilado" || fail=1
exit $fail
