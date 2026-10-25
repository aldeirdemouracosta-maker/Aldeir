# reversa: engenharia reversa automatizada com IA local, em Go

Objetivo: um único binário Go que orquestra ferramentas de análise e um modelo local (Ollama),
registrando cada fato como evidência rastreável. Inspirado no REA, mas sem depender de Node nem de nuvem.

## O que aprendemos de cada projeto

| Projeto | Linguagem | Papel | O que aproveitamos |
|---|---|---|---|
| REA (morluto/rea) | TypeScript/Node | Servidor MCP + CLI, ~50 ferramentas | Ideia central: o agente não adivinha, consulta ferramentas e recebe **evidência + limites** a cada resposta |
| Ghidra | Java | Desmontador e decompilador | Modo `analyzeHeadless` com scripts; projeto persistente evita reanalisar |
| pyghidra-mcp | Python | Ghidra headless via MCP | Servidor persistente (evita custo de iniciar a JVM a cada chamada), busca de strings/símbolos, edição (renomear, tipar) |
| GhidraMCP (LaurieWired) | Java + Python | Plugin da GUI + ponte MCP | Padrão plugin + ponte, mas exige a GUI aberta |
| radare2-mcp, jadx-mcp-server, revula | vários | MCP por ferramenta | Confirmam que cada backend vira um conjunto pequeno de tools |
| GoReSym / redress (GoRE) | Go | Recuperam símbolos e tipos de binários Go | Backend específico para binários Go stripped |
| gapstone (Capstone) | Go (cgo) | Desmontagem em várias arquiteturas | Alternativa embutida ao objdump |

## Decisões de projeto

1. **Interface `Backend` com `Tool`.** Cada programa externo (objdump, Ghidra, rizin, jadx...) implementa `Backend` e expõe tools com descrição, parâmetros e `Limits`. Adicionar uma ferramenta não mexe no agente.
2. **Evidência obrigatória.** Toda chamada de tool vira `evidence.Record` (`[E1]`, `[E2]`...). O prompt exige que o relatório cite essas referências. O log é exportável em JSON (`-evidence`).
3. **Saída cortada em 16 KiB.** Modelos locais têm contexto pequeno; decompilações grandes devem ser paginadas por função.
4. **Ollama via HTTP, só biblioteca padrão.** Sem dependências externas; `llm.Chatter` permite trocar o modelo e simular nos testes.
5. **Ghidra headless por chamada** (primeira versão). Limitação conhecida: cada chamada reimporta com `-overwrite` e custa o tempo de iniciar a JVM. Próximo passo: manter um processo Ghidra vivo (como o pyghidra-mcp faz) e falar com ele por HTTP.

## ROMs

O mesmo desenho serve para ROMs; o que muda é o **carregador** e o **depurador**:

- **Ghidra com loaders da comunidade:** N64, GBA e NES (GhidraNes) têm loaders; o de NES tem suporte limitado a mappers e o bank switching é manual. Para SNES, Game Boy, Mega Drive e Switch existem projetos semelhantes que **não verifiquei nesta sessão**.
- **Emuladores com depurador** (Mesen cobre NES, SNES, Game Boy e GBA): fornecem execução, breakpoints e memória em tempo real. Seriam um `Backend` de análise dinâmica.
- **Fluxo de decompilação de jogos** (splat, decomp.me e o ecossistema de "matching decomp"): conheço pelo uso geral, não os verifiquei aqui. Vale conferir antes de integrar.

Aviso: ROMs e firmware têm direitos autorais. Use ROMs que você mesmo extraiu, homebrew ou pesquisa de interoperabilidade permitida pela lei local.

## Roteiro

- [x] Núcleo: agente, evidências, cliente Ollama, backends objdump e Ghidra (headless), CLI `doctor` e `analyze`
- [ ] Ghidra persistente (processo único, API HTTP) e tools de xrefs, strings, renomear
- [ ] Backends: rizin, jadx/apktool (APK), GoReSym (binários Go), capstone
- [ ] Modo servidor MCP (para usar o `reversa` também no Claude Code)
- [ ] Backend de emulador (ROMs) e análise dinâmica (Frida)
- [ ] Testes de integração com um binário de exemplo e um modelo real
