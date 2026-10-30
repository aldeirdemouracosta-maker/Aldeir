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

## Atualizar (Windows)

Dê dois cliques em `atualizar.bat` (na pasta `reversa`): ele baixa o código novo, recompila e mostra a versão.
Ou, no PowerShell, **dentro da pasta**: `git pull`, depois `go build -o reversa.exe .\cmd\reversa`.

## Qual versão está rodando?

```
./reversa version
```
Mostra o commit e a data do binário (e o rodapé de cada relatório registra a versão que o gerou). Depois de um
`git pull`, é preciso recompilar (`go build -o reversa.exe .\cmd\reversa`) para o binário refletir o código novo.

## Aprofundar uma função

Depois de rodar `ps1`, escolha um endereço do relatório e veja a função com fatos (tamanho, chamadores, funções
chamadas, hardware, laços, strings, stubs) e a desmontagem anotada, sem usar modelo:

```
./reversa func jogo.cue 0x80026538
./reversa func -explain -out funcao.md jogo.cue 0x80026538   # pede também uma hipótese ao modelo
```

Salvar o relatório completo em arquivo: `./reversa ps1 -out relatorio.md jogo.cue`.

## Nomes por evidência

```
./reversa nomes jogo.cue
```
Varre todas as funções e lista só as que têm evidência: stubs de BIOS e de syscall, instaladores de callback (trocam um
ponteiro global e devolvem o antigo) e strings de depuração parecidas com identificadores (como `"CD_cw"`). Nada é
inventado: cada linha cita a evidência, e os nomes são **pistas**, porque o executável não tem símbolos.

## Dados: quem usa um endereço e o que ele contém

```
./reversa xref jogo.cue 0x8002d6d8                 # quem lê, escreve ou monta este endereço
./reversa xref -n 64 jogo.cue 0x8002d640            # todos os acessos a uma tabela de 64 bytes
./reversa mem -n 64 jogo.cue 0x8002d640             # valores iniciais da imagem (tabelas, ponteiros)
```

`xref` mostra o valor escrito quando é constante e marca acessos a tabelas com índice variável. `mem` interpreta as
palavras que parecem endereços (registradores de hardware, funções, strings). Os valores de `mem` são os **iniciais do
arquivo**; a memória em execução pode ter mudado e dados não inicializados (.bss) não estão no arquivo.
As flags (`-n`, `-out`) vêm **antes** do disco e do endereço.

## Escolha do modelo

Em teste com um jogo real, o `qwen2.5-coder:14b` foi ~3,5x mais lento que o 7B e só um pouco melhor. O padrão é o 7B
nos dois estágios. O valor do relatório está nos fatos derivados pelo programa; as hipóteses do modelo ficam marcadas
como não verificadas e são descartadas quando contradizem os fatos.
