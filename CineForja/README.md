# CineForja

Estúdio local multi-agente para gerar/editar vídeo CGI ou stop-motion em hardware limitado
(Tesla P100 16 GB via CUDA + RX 570 8 GB via Vulkan). Orquestração com LangGraph,
persistência em SQLite e Human-in-the-Loop.

**Status: Fase 4 (API + interface) · Fase 3 (modelos reais, não validados em GPU) · Editor FFmpeg (testado)** — grafo, persistência, retomada,
regeneração por consistência, 3 pontos de aprovação, workers CUDA/Vulkan isolados (um modelo
pesado por GPU) e clientes reais para Ollama, ComfyUI e stable-diffusion.cpp. Cada serviço só é
usado se configurado; sem configuração a tarefa continua simulada. Os clientes foram testados
contra servidores falsos; **ainda não foram testados com as GPUs reais**.

## Uso
```
pip install -r requirements.txt
python -m cineforja.cli start demo "um robô aprende a dançar" --style stop_motion
python -m cineforja.cli resume demo
pytest
```

### Com workers em processos separados
```
python -m cineforja.workers.server --kind cuda   --port 8101 &
python -m cineforja.workers.server --kind vulkan --port 8102 &
export CINEFORJA_WORKERS="cuda=http://127.0.0.1:8101,vulkan=http://127.0.0.1:8102"
python -m cineforja.cli start demo "brief" --yes
curl 127.0.0.1:8101/status   # modelo carregado + histórico load/unload
```
Sem `CINEFORJA_WORKERS` as tarefas rodam em processo (modo simulado).

### Modelos reais (variáveis lidas pelos workers)
| Variável | Tarefa | GPU |
|---|---|---|
| `CINEFORJA_OLLAMA_URL`, `CINEFORJA_LLM_MODEL` | Director e ScriptWriter | CUDA |
| `CINEFORJA_OLLAMA_URL`, `CINEFORJA_VLM_MODEL` | ConsistencyChecker (nota 0–10 do frame; vídeos exigem ffmpeg) | CUDA |
| `CINEFORJA_COMFY_URL`, `CINEFORJA_COMFY_WORKFLOW_VIDEO` | Animator | CUDA |
| `CINEFORJA_COMFY_URL`, `CINEFORJA_COMFY_WORKFLOW_IMAGE` | imagem pesada | CUDA |
| `CINEFORJA_SD_BIN`, `CINEFORJA_SD_MODEL` | imagem leve (sd.cpp, build Vulkan) | Vulkan |
| `CINEFORJA_OUTPUT_DIR`, `CINEFORJA_SHOTS` | pasta de saída (padrão `data/projects`), nº de shots (padrão 3) | — |

Workflows do ComfyUI: monte o seu, exporte em **Save (API Format)** e troque os valores do
texto e da semente por `"{{prompt}}"` e `"{{seed}}"`. O CineForja não inclui workflow pronto.
Ollama e ComfyUI dividem a P100: ao trocar de um para o outro o worker descarrega o anterior
(`keep_alive=0` no Ollama, `POST /free` no ComfyUI).

Antes de tudo, rode `python scripts/check_hardware.py` na sua máquina.
Áudio e upscale seguem simulados.

### API e interface web (Fase 4)
```
python -m cineforja.api --db data/cineforja.db --port 8000   # abra http://127.0.0.1:8000
```
Escuta só em `127.0.0.1` e **não tem autenticação**: não exponha na rede.

| Endpoint | Função |
|---|---|
| `POST /projects` `{brief, style, project_id?}` | inicia (em segundo plano) até a 1ª pausa |
| `GET /projects`, `GET /projects/{id}` | lista / estado (`running`, `paused`, `done`, `error`), pausa atual, storyboard, logs |
| `PUT /projects/{id}/storyboard` | edita os shots na pausa "Aprovar storyboard" |
| `POST /projects/{id}/continue` | aprova e segue (também retoma após `error`) |
| `POST /projects/{id}/regenerate` `{shots, prompts?}` | na revisão de frames, refaz só os shots escolhidos |
| `GET /projects/{id}/shots/{n}/media`, `/final` | mídia (só de dentro da pasta de saída) |

A interface (`/`) mostra storyboard editável, frames, notas de consistência, seleção de shots para
refazer, vídeo final e logs. O estado vive no SQLite: reiniciar o servidor não perde projetos.
Um job por projeto; pedidos concorrentes recebem 409.

### Montagem final (Editor)
Quando todos os shots têm arquivo real (vídeo ou imagem), o Editor usa FFmpeg para normalizar
resolução (1280x720), fps (24) e formato, concatenar os shots em ordem (imagens duram 2 s) e,
se houver trilha em arquivo real, mixar o áudio. Grava em `<saída>/<projeto>/final.mp4` via arquivo
temporário (nunca deixa um MP4 parcial). Mídia corrompida falha rápido com erro claro, e o estado
fica salvo no checkpoint para retomar. Sem arquivos reais, o Editor segue simulado.

**Nota de desempenho (para a Fase 5):** o loop atual alterna `video` ↔ `vlm` a cada shot, o que
força descarregar/carregar modelos na P100. Animar todos os shots e só depois checar a consistência em lote reduz as trocas.

## Roadmap
2. ~~Workers CUDA/Vulkan em processos separados (um modelo pesado por vez)~~ ✔
3. Modelos reais (clientes prontos; falta validar nas GPUs): Ollama, ComfyUI (Wan/LTX GGUF) na P100, stable-diffusion.cpp (Vulkan) na RX 570; áudio e upscale pendentes
4. ~~API FastAPI + frontend de aprovação~~ ✔
5. Otimização e presets de estilo

Referências estudadas (não copiadas): HKUDS/ViMax (MIT), leejet/stable-diffusion.cpp (MIT).
