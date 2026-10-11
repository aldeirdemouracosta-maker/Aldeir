# CineForja

Estúdio local multi-agente para gerar/editar vídeo CGI ou stop-motion em hardware limitado
(Tesla P100 16 GB via CUDA + RX 570 8 GB via Vulkan). Orquestração com LangGraph,
persistência em SQLite e Human-in-the-Loop.

**Status: Fase 2 (workers isolados)** — grafo completo, persistência, retomada, regeneração por
consistência, 3 pontos de aprovação e workers CUDA/Vulkan como processos HTTP locais
(127.0.0.1), com no máximo um modelo pesado residente por GPU. Os modelos ainda são simulados.

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

**Nota de desempenho (para a Fase 5):** o loop atual alterna `video` ↔ `vlm` a cada shot, o que
força descarregar/carregar modelos na P100. Animar todos os shots e só depois checar a consistência em lote reduz as trocas.

## Roadmap
2. ~~Workers CUDA/Vulkan em processos separados (um modelo pesado por vez)~~ ✔
3. Modelos reais: llama.cpp/Ollama, ComfyUI (Wan/LTX GGUF) na P100, stable-diffusion.cpp (Vulkan) na RX 570
4. API FastAPI + frontend de aprovação
5. Otimização e presets de estilo

Referências estudadas (não copiadas): HKUDS/ViMax (MIT), leejet/stable-diffusion.cpp (MIT).
