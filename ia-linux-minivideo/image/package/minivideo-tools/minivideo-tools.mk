################################################################################
#
# minivideo-tools — código Python deste repositório (ia-linux-minivideo/)
#
################################################################################

MINIVIDEO_TOOLS_VERSION = 0.3.0
MINIVIDEO_TOOLS_SITE = $(BR2_EXTERNAL_IA_MINIVIDEO_PATH)/..
MINIVIDEO_TOOLS_SITE_METHOD = local
# Copia só o pacote Python: nunca a camada Buildroot (image/, onde pode haver
# uma saída de build de vários GB), testes ou ambientes virtuais.
MINIVIDEO_TOOLS_OVERRIDE_SRCDIR_RSYNC_EXCLUSIONS = \
	--exclude image --exclude tests --exclude docs --exclude .venv \
	--exclude '*.egg-info' --exclude __pycache__ --exclude build
MINIVIDEO_TOOLS_LICENSE = MIT
MINIVIDEO_TOOLS_SETUP_TYPE = setuptools

$(eval $(python-package))
