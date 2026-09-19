################################################################################
#
# ai-shell
#
# Pacote sem código-fonte próprio a compilar: os scripts vivem em
# rootfs-overlay/ (copiados automaticamente pelo Buildroot via
# BR2_ROOTFS_OVERLAY) e llama.cpp é outro pacote Buildroot (upstream).
# Usa SITE_METHOD=local apontando para src/ (apenas um marcador) e um
# INSTALL_TARGET_CMDS vazio — o mesmo mecanismo comprovado usado por
# ai-core (ver ../ai-core/ai-core.mk), para que BR2_PACKAGE_AI_SHELL
# apareça em menuconfig/defconfig e arraste suas dependências via
# 'select' em Config.in sem depender de infraestrutura Buildroot menos
# comum.
#
################################################################################

AI_SHELL_VERSION = 0.8.0
AI_SHELL_SITE = $(BR2_EXTERNAL_IA_LINUX_PATH)/package/ai-shell/src
AI_SHELL_SITE_METHOD = local
AI_SHELL_LICENSE = Apache-2.0
AI_SHELL_LICENSE_FILES = ../../../LICENSE

define AI_SHELL_INSTALL_TARGET_CMDS
	:
endef

$(eval $(generic-package))
