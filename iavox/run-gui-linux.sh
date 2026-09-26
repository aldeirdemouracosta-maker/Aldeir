#!/bin/bash
# Executa a interface gráfica do IAVOX no Linux.
cd "$(dirname "$0")"
python3 -m pip show PyQt5 > /dev/null 2>&1 || pip3 install -r requirements-gui.txt
python3 run_gui.py
