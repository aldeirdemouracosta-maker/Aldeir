# Hardware Research AI Lab (HRAIL) — Fases 0 e 1

Laboratório modular e extensível para pesquisa de hardware (GPU, CPU, NPU…), com CLI em português,
banco SQLite local e política de segurança estrita. **Independente do Peregrinus OS**, mas com
interfaces preparadas para integração futura.

> **Estado: Fase 1 (histórico Git e evidências) sobre a Fase 0.** Somente leitura, análise offline (nível A) e diagnóstico
> leve em espaço de usuário (nível B). Nenhum driver, kernel, firmware, clock ou tensão é tocado.

## Primeiro comando

```sh
cd hardware-research-ai-lab
go build -o bin/hrail ./cmd/hrail && ./bin/hrail doctor
```

Depois: `./bin/hrail init` (cria o banco), `./bin/hrail hardware list`, `./bin/hrail tools check`,
`./bin/hrail report generate`.

Requisitos: Go ≥ 1.24 (o `go.mod` atual declara 1.26 por exigência do driver SQLite puro-Go
`modernc.org/sqlite`; o toolchain foi baixado automaticamente no ambiente de criação). Sem CGO.

## Comandos

| Comando | O que faz |
|---|---|
| `hrail init` | cria `data/hrail.db`, aplica migrações, sincroniza catálogos |
| `hrail doctor` | verifica dependências e permissões **sem alterar nada** |
| `hrail hardware list` / `inspect` | hardware detectado / inventário JSON (`--salvar`, `--saida`) |
| `hrail tools list` / `check` | ferramentas cadastradas / disponibilidade e versão |
| `hrail research sources` / `validar` | catálogo de fontes (`--tipo`, `--json`) / validação |
| `hrail research verificar [--online --clonar --id X]` | confirma fontes online (somente leitura); sem `--online` só mostra o gravado |
| `hrail research historico --fonte X` | analisa commits, reversões, issues e palavras-chave de um clone |
| `hrail research commits` / `evidencia` | consulta achados / registra evidência com URL (decisão humana) |
| `hrail simulation info` | detecta MGPUSim e gem5 (não simula) |
| `hrail compiler info` | inventário Mesa/RADV/NIR/ACO e ferramentas SPIR-V |
| `hrail agents check` | disponibilidade de Ollama e llama.cpp |
| `hrail benchmark selftest` | autoteste de CPU do pipeline (**não** é benchmark de hardware) |
| `hrail experiment list` / `registrar` | consulta / registra experimento de um JSON |
| `hrail banco exportar` | exporta SQLite em JSON ou CSV |
| `hrail report generate` | relatório Markdown + JSON em `reports/` |

`--raiz DIR` (ou `HRAIL_RAIZ`) escolhe o projeto; por padrão sobe a partir do diretório atual até achar `configs/hrail.json`.

## Estrutura

```
cmd/hrail/            CLI
internal/{discovery,research,tools,simulation,compiler,benchmark,experiments,agents,storage,security}
internal/{config,report}   (adicionados: configuração e relatórios)
adapters/{mgpusim,gem5,mesa,vulkan,llama}   adaptadores (Fase 0: detecção + metadados)
catalog/ migrations/ configs/ tests/ scripts/ docs/ reports/
```

Ajustes em relação ao esboço: `catalog/` e `migrations/` são pacotes Go (arquivos embutidos com `go:embed`,
exigem pacote no mesmo diretório); `internal/config` e `internal/report` foram acrescentados.

## Princípios

1. **Nunca presumir hardware**: tudo é detectado; o que não se sabe fica ausente (nunca "falso" inventado).
2. **Origem explícita**: resultados são `measured`, `simulated`, `estimated` ou `fixture`, nunca misturados.
3. **Ausência de evidência ≠ evidência de incompatibilidade.**
4. **IA só sugere**: não aprova mudanças privilegiadas nem declara melhorias sem medições.
5. **Segurança**: sem shell, sem sudo, lista permitida de executáveis, timeout, registro de comandos e códigos de saída.

## Validação

`./scripts/validar.sh` (gofmt, vet, testes, build). Resultados em `reports/VALIDACAO_FASE_0.md`.
Documentação: `docs/` (modelo de implantação e pen drive: `docs/IMPLANTACAO.md`).

**Windows:** a CLI é Linux-only; use `scripts\coletar-windows.ps1` (ver `docs/IMPLANTACAO.md`).
