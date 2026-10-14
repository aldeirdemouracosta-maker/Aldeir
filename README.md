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
| 4 Multimodal (Vision, Speech, Voice, RAG; dependências opcionais) | implementado com backends simulados; backends reais NÃO executados |
| 5 Estabilidade (MemoryManager, Scheduler, Orchestrator, locks, Coordinator) | implementado; 80 testes aprovados |
| 6 Dashboard (HTML/CSS/JS nativos, ~8 KB) | implementado; 89 testes Python + 7 JS aprovados; renderizado em Chromium real |

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

## Multimodal (Fase 4)
Mídia fica em `SWARM_MEDIA` (padrão `~/.swarm/media`); caminhos são relativos a essa pasta. PNG/JPEG ≤10 MB, áudio ≤25 MB,
tipo validado por assinatura. Saídas WAV vão para `out/` e nunca sobrescrevem arquivos.
Pesos/pacotes são opcionais e nunca baixados pelo projeto: `SWARM_VISION_MODEL`, `SWARM_SPEECH_MODEL`,
`SWARM_VOICE_MODEL` + `SWARM_VOICE_VOICES`. Sem eles o agente aparece como indisponível, com o motivo.
RAG usa embeddings do Ollama (`SWARM_EMBED_MODEL`, padrão `nomic-embed-text:latest`) e SQLite.
**Não implementado:** backend de embeddings ONNX. **Não validado:** SmolVLM, Whisper e Kokoro reais.

## Estabilidade (Fase 5)
`/run` passa pelo Orchestrator: fila com prioridade (`high|normal|low`), limite de concorrência (`SWARM_MAX_CONCURRENT`),
fila máxima (`SWARM_MAX_QUEUE`, 429 se cheia), timeout (`SWARM_JOB_TIMEOUT`, 504), cancelamento
(`POST /scheduler/jobs/{id}/cancel`) e admissão por RAM (`SWARM_HEADROOM_MB`). Estado em `GET /scheduler`.
`SWARM_COORD_DIR` ativa o ResourceCoordinator (slots em disco entre processos cooperativos).
Limitações: estimativas de RAM por agente são aproximadas; um job grande pode ser adiado por jobs pequenos
(inanição possível); cancelar/timeout interrompe a espera, mas inferência síncrona em thread (mídia) só termina quando
a thread terminar; locks são cooperativos (não impedem processos alheios).

## Dashboard (Fase 6)
`swarm serve` → http://127.0.0.1:8000/dashboard (ou `/`). Somente leitura: agentes e disponibilidade real, modelos instalados/carregados,
CPU/RAM/GPU/VRAM, fila, limites e histórico de jobs; atualiza a cada 3 s e pausa com a aba oculta.
Segurança: Host validado (anti DNS rebinding), Origin e Fetch Metadata; navegação direta a `/` e `/dashboard` é permitida;
leituras cross-site dos dados são recusadas (403); CSP sem `unsafe-inline`; texto da API só entra via `textContent`.
Testes JS: `node --test tests/js/lib.test.cjs`. Validação visual feita só em Chromium headless no Linux; Windows/Edge/Firefox não testados.
