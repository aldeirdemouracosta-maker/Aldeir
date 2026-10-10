# Códice

Sistema Debian 13 enxuto, só para código, com IA local (llama.cpp + Vulkan), pensado
para o X79 / Xeon E5-2630L v2 (sem AVX2) e RX 580. Interface em verde sobre preto, no
estilo do filme Matrix.

Inclui: kernel XanMod x64v2 (com o do Debian de reserva), LibreWolf, Tor, LibreOffice,
Flatpak + apt + gh, Aether (agente de código), aider e o proxy de correção da Fábrica.

- `build/`              scripts do live-build (NÃO TESTADOS: veja `docs/REVISAO.md`)
- `aether/`             agente de código Aether (tema verde aplicado em `gui/styles.py`)
- `fabrica-correcoes/`  proxy da Fábrica (22 testes passando)
- `docs/`               revisão dos scripts e pesquisa de Hackintosh X79 (estudo)

Build (host Debian/Ubuntu, root, rede):
    cd build && sudo LLAMA_TAG=<tag> DESKTOP=minimal ./build-iso.sh
