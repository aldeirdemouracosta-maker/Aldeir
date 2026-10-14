# Fase 0 — diagnóstico
- `swarm-lite-ai` remoto: vazio (sem commits). `microagents-ai` remoto: vazio. `Aldeir`: não relacionado.
- Backups locais de microagents: nenhum encontrado no ambiente.
- Ambiente (sandbox Linux, não o Windows 11 do proprietário): Python 3.13, git 2.43, uv, 4 CPUs, 16 GB RAM, sem GPU, sem Ollama.
- Dependências instaladas em `.venv` (ignorado pelo git): fastapi, uvicorn, typer, rich, httpx, pyyaml, psutil, pytest.
- Riscos: inferência real não testável aqui (sem Ollama); Windows 11 não testado; TestRunner futuro não é sandbox.
