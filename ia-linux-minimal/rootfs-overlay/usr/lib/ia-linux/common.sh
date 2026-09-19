# shellcheck shell=ash
# Funções compartilhadas pelos comandos ia-* (ia-shell, ia-model, ia-chat,
# ia-benchmark, ia-server, ia-gpu). Não é um script executável — é
# carregado via `. /usr/lib/ia-linux/common.sh`.

# shellcheck disable=SC2034  # usadas pelos scripts que fazem `. common.sh`
DATA_DIR="${IA_DATA_DIR:-/data}"
MODELS_DIR="${DATA_DIR}/models"
SESSIONS_DIR="${DATA_DIR}/sessions"
LOG_DIR="${DATA_DIR}/logs"

# Envia um comando ao ai-core (modo cliente) e imprime a resposta.
# Uso: ia_core STATUS
#      ia_core MODEL SELECT 2
ia_core() {
    ai-core "$@"
}

# Extrai o valor de uma chave "chave=valor" da saída de `ia_core`.
# Uso: threads=$(ia_core HW | ia_core_field threads_efetivas)
ia_core_field() {
    key="$1"
    grep "^${key}=" | head -n1 | cut -d= -f2-
}

die() {
    echo "erro: $*" >&2
    exit 1
}

require_active_model_path() {
    name="$(ia_core MODEL ACTIVE 2>/dev/null)"
    if [ -z "${name}" ] || [ "${name}" = "nenhum modelo ativo" ]; then
        die "nenhum modelo ativo. Use: ia-model select <indice> (ver 'ia-model list')"
    fi
    path="${MODELS_DIR}/${name}"
    if [ ! -f "${path}" ]; then
        die "modelo ativo '${name}' não encontrado em ${MODELS_DIR}"
    fi
    echo "${path}"
}
