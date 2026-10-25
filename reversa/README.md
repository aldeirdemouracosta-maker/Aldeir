# reversa

Engenharia reversa automatizada com IA local. Veja `docs/ARQUITETURA.md`.

```
go build -o reversa ./cmd/reversa
./reversa doctor
ollama pull qwen2.5-coder:14b
./reversa analyze -evidence ev.json /caminho/do/binario
```

Para usar o Ghidra: `export GHIDRA_INSTALL_DIR=/opt/ghidra` e rode a partir da pasta `reversa/` (os scripts ficam em `scripts/ghidra`).
