################################################################################
#
# rife-ncnn-vulkan-bin — binário pré-compilado do release oficial
#
################################################################################

RIFE_NCNN_VULKAN_BIN_VERSION = 20221029
RIFE_NCNN_VULKAN_BIN_SOURCE = rife-ncnn-vulkan-$(RIFE_NCNN_VULKAN_BIN_VERSION)-ubuntu.zip
RIFE_NCNN_VULKAN_BIN_SITE = https://github.com/nihui/rife-ncnn-vulkan/releases/download/$(RIFE_NCNN_VULKAN_BIN_VERSION)
RIFE_NCNN_VULKAN_BIN_LICENSE = MIT
RIFE_NCNN_VULKAN_BIN_LICENSE_FILES = LICENSE
RIFE_NCNN_VULKAN_BIN_DEPENDENCIES = vulkan-loader
RIFE_NCNN_VULKAN_BIN_MODELS = rife-v4.6

define RIFE_NCNN_VULKAN_BIN_EXTRACT_CMDS
	$(UNZIP) -d $(@D) $(RIFE_NCNN_VULKAN_BIN_DL_DIR)/$(RIFE_NCNN_VULKAN_BIN_SOURCE)
	mv $(@D)/rife-ncnn-vulkan-$(RIFE_NCNN_VULKAN_BIN_VERSION)-ubuntu/* $(@D)/
endef

define RIFE_NCNN_VULKAN_BIN_INSTALL_TARGET_CMDS
	$(INSTALL) -D -m 0755 $(@D)/rife-ncnn-vulkan $(TARGET_DIR)/usr/bin/rife-ncnn-vulkan
	for m in $(RIFE_NCNN_VULKAN_BIN_MODELS); do \
		mkdir -p $(TARGET_DIR)/usr/share/minivideo/modelos/rife/$$m && \
		cp -a $(@D)/$$m/. $(TARGET_DIR)/usr/share/minivideo/modelos/rife/$$m/ || exit 1; \
	done
endef

$(eval $(generic-package))
