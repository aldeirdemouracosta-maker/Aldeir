# CineForja

Estúdio local multi-agente para gerar/editar vídeo CGI ou stop-motion em hardware limitado
(Tesla P100 16 GB via CUDA + RX 570 8 GB via Vulkan). Orquestração com LangGraph,
persistência em SQLite e Human-in-the-Loop.

**Status: Fase 1 (fundação)** — grafo completo com nós simulados, persistência, retomada,
regeneração por consistência e 3 pontos de aprovação. Nenhum modelo real ainda.

## Uso
```
pip install -r requirements.txt
python -m cineforja.cli start demo "um robô aprende a dançar" --style stop_motion
python -m cineforja.cli resume demo
pytest
```

## Roadmap
2. Workers CUDA/Vulkan em processos separados (um modelo pesado por vez)
3. Modelos reais: llama.cpp/Ollama, ComfyUI (Wan/LTX GGUF) na P100, stable-diffusion.cpp (Vulkan) na RX 570
4. API FastAPI + frontend de aprovação
5. Otimização e presets de estilo

Referências estudadas (não copiadas): HKUDS/ViMax (MIT), leejet/stable-diffusion.cpp (MIT).
