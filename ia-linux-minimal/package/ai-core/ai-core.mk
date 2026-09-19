################################################################################
#
# ai-core
#
################################################################################

AI_CORE_VERSION = 0.6.0
# Fonte local: ai-core/ vive dentro deste BR2_EXTERNAL, não é baixado.
AI_CORE_SITE = $(BR2_EXTERNAL_IA_LINUX_PATH)/ai-core
AI_CORE_SITE_METHOD = local
AI_CORE_LICENSE = Apache-2.0
AI_CORE_LICENSE_FILES = LICENSE

$(eval $(cargo-package))
