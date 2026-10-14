# Auditoria do projeto (critério: simples, mas completo — estilo Go)

Método: busca automática de definições sem uso, leitura de cada módulo contra as regras de segurança do
projeto e uma suíte nova para cada correção. Resultado medido: 156 testes Python + 7 JavaScript aprovados.

## Removido (não tinha função)
| Item | Por quê |
|---|---|
| `TaskRequest` | nenhum chamador |
| preferências do `StateStore` (`get_pref/set_pref`) | nada as usava; o estado dos agentes já cobre a configuração |
| resumo de `SessionMemory` | nada produzia o resumo |
| `LimitedProcess.cancel` | nenhum chamador; o que faltava era matar o filho no Ctrl+C (corrigido abaixo) |
| `Slot.renew` (coordenador) | nada renovava; o risco real era o lease curto (corrigido abaixo) |
| `sine`/`wav_info` no app | só testes usavam; foram para `tests/helpers.py` |

## Corrigido (falhas reais encontradas)
1. Host `testserver` era aceito na configuração de produção.
2. Origin era comparado só pelo hostname: outro app local em outra porta (ou `https`) passava. Agora exige origem idêntica (esquema+host+porta).
3. Lease do coordenador (300 s) podia expirar antes do `job_timeout` configurado; agora `ttl = 2×timeout + 60`.
4. Ctrl+C durante `/test` deixava o pytest órfão.
5. Corpo de requisição sem limite (agora 1 MB por `Content-Length`; ver limitações).
6. Job que nunca consegue RAM esperava na fila para sempre; agora sai com 504 após `SWARM_QUEUE_TIMEOUT`.
7. Erro do Manager era identificado por texto; agora é tipado (`UnknownAgent`).
8. Cliente HTTP do provedor nunca era fechado.
9. Uma pasta com um arquivo ruim travava a indexação inteira; agora o arquivo é ignorado e relatado (pedido direto continua dando erro).

## Acrescentado (faltava e tem função)
| Item | Função |
|---|---|
| 4 agentes: OCR, LangID, Planner/Tool, Retrieval | completam os 10; LangID e Planner são reais, OCR e Retrieval dependem de pesos opcionais |
| Coder `output_mode: code_only` | rejeita Markdown/explicação extra (problema relatado no PDF) |
| `Orchestrator.run_nested` | passos de plano sem deadlock com 1 slot, reservando RAM |
| `configs/models.yaml` + `swarm models` | manifesto de referência por agente, instalação de arquivo único com SHA-256, limite de 1 GB, hosts oficiais, retomada |
| `evals/*.yaml` + `swarm tune` | avaliação e ajuste sem tocar nos pesos |
| `POST /feedback` | 👍/👎 por job, sem guardar conteúdo |
| `scripts/check.py` | testes + arquivos grandes + segredos + pesos/.env versionados antes do push |
| `.github/workflows/swarm-ci.yml` | testes em Ubuntu e **Windows** |
| `.env.example`, extras opcionais no `pyproject` | documentam variáveis e backends |
| `swarm status`, `swarm models` | visão rápida pelo terminal |

## Avaliado e deliberadamente NÃO adicionado
AgentScope / Qwen-Agent (o PDF recomenda só como referência), LightRAG, MNN, fine-tuning (regra do projeto),
sandbox Docker, autenticação por token (acesso é só loopback), OpenTelemetry/Prometheus, ORM, Redis, WebSocket/streaming,
framework de frontend, sistema de plugins. Nenhum resolve um problema que o projeto tenha hoje.

## Achados fora do SWARM (não alterei)
- `lumivox/app/release/lumivox-release.keystore` está versionado e o `lumivox/app/build.gradle` traz a senha padrão em texto.
  Quem tem o repositório pode assinar APKs como você. Sugestão: gerar um keystore novo, guardá-lo fora do Git (secrets do CI) e
  tratar o atual como comprometido.
- O workflow do Lumivox usa `actions/checkout@v7`, `setup-java@v5` e `gradle/actions/setup-gradle@v6`; não verifiquei se essas versões existem.

## Limitações conhecidas
- O limite de 1 MB do corpo só vale quando há `Content-Length` (uvicorn não limita corpo em chunks).
- Estimativas de RAM por agente são aproximadas; um job grande pode ser adiado por jobs pequenos (inanição).
- Inferência síncrona em thread (mídia) não é interrompida por timeout/cancelamento; só a espera é.
- LangID identifica pt/en/es/fr/de/it/ja/zh/ko/ru por script e palavras funcionais: textos curtos ou mistos dão `und`. Medido em 19 frases
  (10 escritas depois do ajuste): 19/19 — amostra pequena, não é garantia.
- Planner com modelo de 0,5B falha em gerar JSON com frequência; `plan_run` aceita passos escritos à mão e valida tudo antes de executar.
- O pacote se chama `app` (herdado da estrutura de referência); evite instalar fora de um venv.
- Ainda **não validados em hardware real**: Ollama, SmolVLM, Whisper, Kokoro, PaddleOCR, Chinese-CLIP, Windows 11, workflow do GitHub Actions.
- Sem adaptadores ainda (`status: planned` no manifesto): ReazonSpeech, SenseVoice, MeloTTS, Piper pt-BR, BGE/Ruri via Transformers.
- Nenhum SHA-256 de modelo foi verificado (o ambiente não alcança o Hugging Face); o instalador exige que você informe o hash.
