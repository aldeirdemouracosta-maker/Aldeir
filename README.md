# SWARM LITE AI

Reconstrução do MICROAGENTS AI (referência v0.5.3). Agentes locais, minimalistas e supervisionados.

> **Estado honesto:** o código do MICROAGENTS AI original não estava disponível. Nada foi recuperado;
> tudo aqui é reimplementação incremental. Os números históricos (174 testes Python etc.) **não** valem para este projeto.

## Status das fases
| Fase | Estado |
|---|---|
| 0 Diagnóstico | feito (ver `docs/fase0.md`) |
| 1 Núcleo (API, CLI, Chat, Coder, Ollama, Registry/Router) | implementado, 13 testes aprovados |
| 2 Coding Terminal (workspace, patches, runner, memória) | implementado; 37 testes no total aprovados |
| 3 Gerenciamento (AgentManager, ModelManager, StateStore, recursos, Origin/Fetch Metadata) | implementado; 47 testes aprovados |
| 4–6 | não iniciadas |

## Uso
```
python -m venv .venv && .venv/bin/pip install -e .[dev]     # Windows: .venv\Scripts\pip
swarm agents        # agentes e disponibilidade real
swarm run summarize "texto"
swarm serve         # 127.0.0.1:8000
pytest
```
Provedor: `SWARM_PROVIDER=ollama|local_compatible`, `SWARM_PROVIDER_URL=...`. Modelos em `configs/agents.yaml`;
o projeto nunca baixa modelos sozinho.

## Segurança (já presente na Fase 1)
Bind em loopback, validação de Host (`TrustedHostMiddleware`), Coder só devolve texto, sem endpoint de execução de comandos.

## Coding Terminal (Fase 2)
`swarm terminal --root .` → fluxo `/edit → /diff → /apply → /test → /undo`.
O modelo só **propõe** texto; `/apply` pede confirmação humana, faz backup em `.swarm/backups` e `/undo` restaura.
Nenhuma saída de modelo é executada. `/test` roda apenas `pytest` com timeout — **não é um sandbox**:
os testes do projeto executam código com as suas permissões.
