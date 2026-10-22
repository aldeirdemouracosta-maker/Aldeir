# Arquitetura

```
                       ┌────────────────────────── cmd/hrail (CLI pt-BR) ──────────────────────────┐
                       │                                                                            │
 discovery ──┐         │                                                                            │
 tools ──────┤         ▼                                                                            ▼
 research ───┼──► storage (SQLite + migrações) ◄── experiments (mapa de risco) ◄── benchmark ──► report
 simulation ─┤         ▲                                   ▲
 compiler ───┤         │                                   │
 agents ─────┘    security (Runner: timeout, allow-list, auditoria, ConfinePath)
        ▲
  adapters/* (mgpusim, gem5, mesa, vulkan, llama) implementam tools.Adapter
```

## Decisões

- **Go puro, sem CGO**: `modernc.org/sqlite`; único módulo de terceiros relevante.
- **Coleta somente leitura**: CPU/RAM via `/proc`, armazenamento e PCIe via `/sys`, Vulkan via `vulkaninfo` (lista permitida).
  A raiz do sistema de arquivos é injetável (`Collector.Root`), o que permite testar com hardware fictício; nesse modo
  o inventário é marcado `origin=fixture`.
- **Uma única porta de execução** (`security.Runner`): sem shell; recusa `sudo`/`su`; só executa binários do catálogo
  (`tools.AllowList`); timeout com encerramento do grupo de processos; saída limitada a 1 MiB; registra comando, argumentos,
  código de saída, duração e timeout — **nunca a saída** (pode conter dados pessoais). Registros vão para `command_log`.
- **Confinamento**: banco, relatórios e exportações passam por `security.ConfinePath` (dentro da raiz do projeto).
- **Dados desconhecidos**: ponteiros/`omitempty` + `unavailable`/`not_determined`. Campos inferidos por PCI ID levam `*_source: inferido_pci_id`.
- **Níveis de risco**: `config.Validate` recusa habilitar C/D/E; `experiments.Classify` os bloqueia em duas camadas.
- **Migrações**: arquivos `NNNN_nome.sql` embutidos, aplicados em ordem, cada um em transação, registrados em `schema_migrations`.
- **Banco**: `data/hrail.db` (ignorado pelo git). Tabelas: `hardware_snapshots`, `sources`, `tools`, `experiments`, `evidences`, `results`, `command_log`.
  `CHECK` no esquema impede origens, estados e níveis inválidos.

## Integração futura com o Peregrinus OS

Nenhuma dependência existe hoje. Pontos de extensão previstos: `tools.Adapter` (novos adaptadores), `agents.Provider`,
exportação JSON/CSV estável, e a CLI como processo externo. A integração deve ocorrer via contratos JSON versionados.
