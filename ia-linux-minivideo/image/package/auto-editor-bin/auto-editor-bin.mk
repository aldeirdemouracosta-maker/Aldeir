################################################################################
#
# auto-editor-bin — binário pré-compilado do release oficial
#
################################################################################

AUTO_EDITOR_BIN_VERSION = 31.6.0
AUTO_EDITOR_BIN_SOURCE = auto-editor-linux-x86_64
AUTO_EDITOR_BIN_SITE = https://github.com/WyattBlue/auto-editor/releases/download/$(AUTO_EDITOR_BIN_VERSION)
AUTO_EDITOR_BIN_LICENSE = Unlicense

# O download é o próprio executável (sem arquivo compactado).
define AUTO_EDITOR_BIN_EXTRACT_CMDS
	cp $(AUTO_EDITOR_BIN_DL_DIR)/$(AUTO_EDITOR_BIN_SOURCE) $(@D)/auto-editor
endef

define AUTO_EDITOR_BIN_INSTALL_TARGET_CMDS
	$(INSTALL) -D -m 0755 $(@D)/auto-editor $(TARGET_DIR)/usr/bin/auto-editor
endef

$(eval $(generic-package))
