# SWARM LITE AI

Reconstrução do MICROAGENTS AI (referência v0.5.3). Agentes locais, minimalistas e supervisionados.

> **Estado honesto:** o código do MICROAGENTS AI original não estava disponível. Nada foi recuperado;
> tudo aqui é reimplementação incremental. Os números históricos (174 testes Python etc.) **não** valem para este projeto.

## Status
| Bloco | Estado |
|---|---|
| Fases 0–6 (núcleo, terminal supervisionado, gerenciamento, multimodal, estabilidade, dashboard) | implementadas |
| 10 agentes: chat, coder, vision, speech, voice, rag, ocr, langid, planner, retrieval | registrados; disponibilidade real por agente |
| Auditoria (`docs/auditoria.md`) | feita: código morto removido, 9 falhas corrigidas |
| Autotreinamento sem tocar pesos (`swarm tune`, `evals/`, `/feedback`) | implementado |
| Testes | 156 Python + 7 JavaScript aprovados (backends reais simulados) |
| Hardware real (Ollama, modelos, Windows 11, CI) | **não validado** |

## Uso
```
python -m venv .venv && .venv/bin/pip install -e .[dev]     # Windows: .venv\Scripts\pip
swarm status        # resumo do runtime
swarm agents        # agentes e disponibilidade real
swarm models        # modelos de referência (instalar: swarm models install ID --sha256 ...)
swarm tune chat     # avalia modelos instalados e recomenda (--apply troca)
swarm run summarize "texto"
swarm serve         # 127.0.0.1:8000
python scripts/check.py   # antes de cada push: testes, segredos, arquivos grandes
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

## Agentes e modelos de referência
Fonte: PDF de pesquisa (modelos < 1 GB). Detalhes, tamanhos e licenças em `configs/models.yaml`.
| Agente | Função | Referência | Adaptador |
|---|---|---|---|
| chat | conversa, resumo, tradução | Qwen2.5-0.5B-Instruct (GGUF) | pronto (Ollama / llama-server) |
| coder | código, revisão, `code_only` | Qwen2.5-Coder-0.5B-Instruct | pronto |
| vision | descrição de imagem | SmolVLM (original) | pronto, não validado |
| ocr | texto em imagens | PP-OCR (PaddleOCR) | pronto, não validado |
| speech | transcrição | Whisper Tiny; ReazonSpeech / SenseVoice (ref.) | Whisper pronto; outros planejados |
| voice | síntese WAV | Kokoro; Piper pt-BR / MeloTTS (ref.) | Kokoro pronto; outros planejados |
| rag | busca semântica com referência | nomic-embed-text (Ollama); BGE / Ruri (ref.) | Ollama pronto; outros planejados |
| langid | idioma do texto | heurística própria, sem modelo | pronto e medido |
| retrieval | imagens por texto | Chinese-CLIP | pronto, não validado |
| planner | plano de até 5 passos entre as ações | Qwen2.5 (JSON) | pronto; `plan_run` com passos manuais |

## Autotreinamento (sem alterar pesos)
`evals/<agente>.yaml` define casos objetivos. `swarm tune <agente>` mede acerto e latência de cada modelo instalado,
guarda o resultado e recomenda; só `--apply` troca o modelo (com margem mínima de 10 pontos sobre o atual para não trocar por ruído).
`POST /feedback {job_id, rating: 1|-1}` registra a opinião por agente/modelo (sem guardar texto). Fine-tuning não existe e exige autorização explícita.
