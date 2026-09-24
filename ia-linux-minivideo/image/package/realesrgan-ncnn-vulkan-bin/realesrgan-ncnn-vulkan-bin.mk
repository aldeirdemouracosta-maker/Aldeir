################################################################################
#
# realesrgan-ncnn-vulkan-bin — binário pré-compilado do release oficial
#
################################################################################

REALESRGAN_NCNN_VULKAN_BIN_VERSION = 20220424
REALESRGAN_NCNN_VULKAN_BIN_SOURCE = realesrgan-ncnn-vulkan-$(REALESRGAN_NCNN_VULKAN_BIN_VERSION)-ubuntu.zip
REALESRGAN_NCNN_VULKAN_BIN_SITE = https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0
REALESRGAN_NCNN_VULKAN_BIN_LICENSE = BSD-3-Clause
REALESRGAN_NCNN_VULKAN_BIN_DEPENDENCIES = vulkan-loader

define REALESRGAN_NCNN_VULKAN_BIN_EXTRACT_CMDS
	$(UNZIP) -d $(@D) $(REALESRGAN_NCNN_VULKAN_BIN_DL_DIR)/$(REALESRGAN_NCNN_VULKAN_BIN_SOURCE)
endef

# O zip oficial vem sem bit de execução: install -m 0755 corrige.
define REALESRGAN_NCNN_VULKAN_BIN_INSTALL_TARGET_CMDS
	$(INSTALL) -D -m 0755 $(@D)/realesrgan-ncnn-vulkan $(TARGET_DIR)/usr/bin/realesrgan-ncnn-vulkan
	mkdir -p $(TARGET_DIR)/usr/share/minivideo/modelos/realesrgan/models
	cp -a $(@D)/models/. $(TARGET_DIR)/usr/share/minivideo/modelos/realesrgan/models/
endef

$(eval $(generic-package))
