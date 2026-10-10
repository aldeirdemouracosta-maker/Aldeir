# Kit: distro enxuta para IA local (Debian 13 + XanMod LTS x64v2)

Conteúdo:
- `CLAUDE.md`           contexto e regras para o Claude Code
- `PROMPT-INICIAL.md`   prompt para iniciar
- `build/`              scripts do live-build (RASCUNHO, NÃO TESTADO)
- `docs/achados-hackintosh-x79.pdf` e `.md`  pesquisa Hackintosh X79 (material de estudo, fora da ISO)

Uso rápido (host Debian/Ubuntu, com root e ~15 GB livres):
    cd build && sudo DESKTOP=minimal ./build-iso.sh     # ou DESKTOP=none
A ISO sai em `build/work/`. Teste em VM (QEMU) antes de gravar em pendrive.
