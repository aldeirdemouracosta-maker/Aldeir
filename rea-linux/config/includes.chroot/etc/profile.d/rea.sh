# shellcheck shell=sh
# Variaveis do REA Linux
export GHIDRA_INSTALL_DIR=/opt/ghidra/atual
export REA_EXTENSAO_GHIDRAMCP=/opt/ghidra-mcp/ext/GhidraMCP/lib/GhidraMCP.jar
export REA_PROJETOS="$HOME/rea-projetos"
case ":$PATH:" in
    *:/usr/local/bin:*) ;;
    *) export PATH="/usr/local/bin:$PATH" ;;
esac
if [ -d /opt/rea/venv/bin ]; then
    export REA_PYTHON=/opt/rea/venv/bin/python
else
    export REA_PYTHON=/usr/bin/python3
fi
