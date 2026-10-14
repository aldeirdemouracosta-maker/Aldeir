# Instalação e teste de fumaça

Python **3.11 ou superior** é obrigatório. Ubuntu 22.04 vem com 3.10: use o 24.04 ou instale um Python mais novo.
Tudo foi testado em **Linux (Python 3.13)**. Os passos de Windows/PowerShell abaixo **não foram executados**.

## Linux (Ubuntu/Debian) — recomendado
```bash
sudo apt update && sudo apt install -y python3 python3-venv git curl
python3 --version                  # precisa mostrar 3.11 ou mais

git clone --branch claude/pensive-cannon-umh9g3 https://github.com/aldeirdemouracosta-maker/Aldeir.git swarm
cd swarm
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python scripts/check.py            # testes Python e JS, segredos, arquivos grandes

# Servidor de modelos (o SWARM nunca baixa modelos sozinho). Instalador oficial do Ollama:
curl -fsSL https://ollama.com/install.sh | sh      # prefira ler o script antes de executar
ollama pull qwen2.5:0.5b
ollama pull qwen2.5-coder:0.5b
ollama pull nomic-embed-text

python scripts/smoke.py 2>&1 | tee smoke.txt       # cole o smoke.txt de volta para análise
swarm serve                                        # http://127.0.0.1:8000/dashboard
```

## Windows (PowerShell) — não testado
```powershell
winget install -e --id Python.Python.3.13          # IDs do winget não verificados; se falhar, use os instaladores oficiais
winget install -e --id Git.Git
winget install -e --id Ollama.Ollama
# feche e reabra o PowerShell; se "python" abrir a Microsoft Store, desative o alias em Configurações > Aplicativos > Aliases

git clone --branch claude/pensive-cannon-umh9g3 https://github.com/aldeirdemouracosta-maker/Aldeir.git swarm
cd swarm
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass     # só nesta janela, para permitir o Activate.ps1
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
$env:PYTHONUTF8 = "1"
python scripts/check.py

ollama pull qwen2.5:0.5b
ollama pull qwen2.5-coder:0.5b
ollama pull nomic-embed-text

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8       # PowerShell 5.1: evita acentos quebrados ao redirecionar
python scripts/smoke.py 2>&1 | Tee-Object -FilePath smoke.txt
swarm serve
```
Se o repositório for privado, o Git pedirá login do GitHub na primeira vez.

## Depois do teste de fumaça
- `swarm status` — resumo do runtime · `swarm agents` — agentes e motivo de indisponibilidade
- `swarm chat --session ana` — conversa com memória · `swarm tune chat` — compara os modelos instalados
- Para comparar com o Qwen3: `ollama pull qwen3:0.6b` e `swarm tune chat --models qwen2.5:0.5b,qwen3:0.6b`
- PDF/DOCX no RAG: `pip install -e ".[docs]"` (já incluído em `.[dev]`)
