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

## Aprofundar uma função

Depois de rodar `ps1`, escolha um endereço do relatório e veja a função com fatos (tamanho, chamadores, funções
chamadas, hardware, laços, strings, stubs) e a desmontagem anotada, sem usar modelo:

```
./reversa func jogo.cue 0x80026538
./reversa func -explain -out funcao.md jogo.cue 0x80026538   # pede também uma hipótese ao modelo
```

Salvar o relatório completo em arquivo: `./reversa ps1 -out relatorio.md jogo.cue`.

## Escolha do modelo

Em teste com um jogo real, o `qwen2.5-coder:14b` foi ~3,5x mais lento que o 7B e só um pouco melhor. O padrão é o 7B
nos dois estágios. O valor do relatório está nos fatos derivados pelo programa; as hipóteses do modelo ficam marcadas
como não verificadas e são descartadas quando contradizem os fatos.
