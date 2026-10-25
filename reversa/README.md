# reversa

Engenharia reversa automatizada com IA local. Veja `docs/ARQUITETURA.md`.

```
go build -o reversa ./cmd/reversa
./reversa doctor
ollama pull qwen2.5-coder:14b
./reversa analyze -evidence ev.json /caminho/do/binario
```

Para usar o Ghidra: `export GHIDRA_INSTALL_DIR=/opt/ghidra` e rode a partir da pasta `reversa/` (os scripts ficam em `scripts/ghidra`).

## PS1 e MCP

```
./reversa disc jogo.cue                 # volume, boot e arquivos da raiz
./reversa ps1 -evidence ev.json jogo.cue # pipeline com modelos locais (exe, cue, bin ou iso)
./reversa mcp -root ~/jogos             # servidor MCP por stdio; só lê dentro da pasta
```

Registro no Claude Code: `claude mcp add reversa -- /caminho/reversa mcp -root ~/jogos`.
