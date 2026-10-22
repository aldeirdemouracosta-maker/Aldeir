# Validação da Fase 0

Data: 2026-10-22 · Comando: `./scripts/validar.sh`

| Verificação | Resultado |
|---|---|
| `gofmt -l .` | sem diferenças |
| `go vet ./...` | sem avisos |
| `go test ./... -count=1` | **53 testes, 0 falhas** (12 pacotes com testes) |
| `go build -o bin/hrail ./cmd/hrail` | compilou |

Toolchain: Go 1.26.0 (baixado automaticamente porque `modernc.org/sqlite` exige ≥ 1.26; o Go local era 1.24.7).

## Cobertura de testes por requisito

| # | Requisito | Onde |
|---|---|---|
| 1 | Inicialização e configuração | `internal/config`, `tests` (config com nível C é recusada) |
| 2 | Criação e migração do SQLite | `internal/storage` (v1→v2 incremental, idempotência, CHECKs) |
| 3 | Catálogo de ferramentas | `internal/tools` (embutido válido, duplicatas, regex inválido, estados) |
| 4 | Validação de fontes | `internal/research` |
| 5 | Diagnóstico com ferramentas ausentes | `tools`, `compiler`, `simulation`, `agents`, `tests` (PATH vazio) |
| 6 | Hardware fictício | `internal/discovery` (árvore `WriteFixture`, `vulkaninfo` fictício) |
| 7 | Exportação JSON | `discovery` (ida e volta), `storage`, `tests` (JSON/CSV, caminho fora do projeto recusado) |
| 8 | Registro e consulta de experimentos | `internal/experiments`, `tests` |
| 9 | Classificação de risco | `internal/experiments` (A/B; C/D/E bloqueados; estados de evidência) |
| 10 | Falhas e timeouts de processos | `internal/security` (exit≠0, timeout com grupo de processos, inexistente, sudo, limite de saída), `tools` |

Cobertura de instruções (go test -cover): security 91%, discovery 88%, benchmark 88%, research 86%, experiments 80%,
config 79%, storage 77%, tools 72%, agents 68%, compiler 96%, simulation 100%. `cmd/hrail` é coberto por testes de ponta
a ponta (binário real), que não entram nessa métrica; `internal/report` e `adapters/*` só indiretamente.

## O que funciona (verificado)

- CLI: `doctor`, `init`, `hardware list/inspect`, `tools list/check`, `research sources/validar`, `simulation info`,
  `compiler info`, `agents check`, `benchmark selftest`, `experiment list/registrar`, `banco exportar`, `report generate`.
- SQLite local com 2 migrações; `command_log` registra cada processo externo (comando, argumentos, código, duração, timeout).
- Autoteste de CPU rodou no ambiente real (≈ 4 milhões de hashes/s nesta VM), marcado **infraestrutura**.
- Ferramentas ausentes são informadas, nunca mascaradas.

## O que NÃO foi validado / permanece planejado

- **Nenhum teste em hardware real com GPU**: a RX 580 2048SP só foi exercitada com dados fictícios.
- Parser do `vulkaninfo` testado só contra saída fictícia; formatos reais variam.
- Fontes externas não verificadas online (rede bloqueada).
- `internal/report` não tem teste unitário próprio (coberto pelo teste de ponta a ponta).
- Todo o restante é planejado nas fases 1–8 (`docs/ROADMAP.md`): análise Git, simulação, compiladores Mesa, benchmarks Vulkan,
  agentes de IA, validação de otimizações, outros componentes. Níveis C/D/E permanecem **desativados**.

## Conformidade com as regras de segurança

Sem sudo; sem alteração de kernel/módulos/firmware/BIOS/initramfs/drivers; sem mexer em energia/clock/tensão; sem downloads de
dependências do laboratório (apenas o módulo Go de SQLite, em tempo de build); nenhum código de terceiros executado;
timeout em todo comando externo; banco e relatórios confinados ao projeto; dados fictícios marcados `fixture`.
