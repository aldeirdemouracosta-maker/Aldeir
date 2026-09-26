#!/bin/bash
# Executa a interface gráfica do IAVOX no Linux.
# Na primeira vez: cria o ambiente Python (.venv), atualiza o pip (o pip 22
# do Ubuntu 22.04 tem um bug que trava a instalação) e instala as dependências.
set -e
cd "$(dirname "$0")"

if [ ! -x .venv/bin/python ]; then
    echo "Criando o ambiente Python (.venv)..."
    python3 -m venv .venv
fi
PY=.venv/bin/python

if ! $PY -c "import PyQt5, pdfplumber" 2>/dev/null; then
    echo "Instalando dependências (primeira execução, pode demorar)..."
    $PY -m pip install --upgrade pip
    $PY -m pip install -r requirements.txt -r requirements-gui.txt
fi

if ! $PY -c "import sounddevice, faster_whisper" 2>/dev/null; then
    echo "Instalando a parte de voz (FalaVox)..."
    $PY -m pip install -r requirements-voz.txt || \
        echo "AVISO: a parte de voz não foi instalada; o FalaVox vai pedir para digitar a resposta."
fi

exec $PY run_gui.py "$@"
