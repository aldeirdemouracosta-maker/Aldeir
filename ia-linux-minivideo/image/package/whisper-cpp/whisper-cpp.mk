################################################################################
#
# whisper-cpp — mesmo padrão do pacote llama-cpp do Buildroot 2026.08
#
################################################################################

WHISPER_CPP_VERSION = 1.9.4
WHISPER_CPP_SOURCE = v$(WHISPER_CPP_VERSION).tar.gz
WHISPER_CPP_SITE = https://github.com/ggml-org/whisper.cpp/archive/refs/tags
WHISPER_CPP_LICENSE = MIT
WHISPER_CPP_LICENSE_FILES = LICENSE
# Instruções de CPU vêm do -march do toolchain (BR2_x86_corei7_avx: AVX,
# sem AVX2/FMA/F16C). GGML_NATIVE já é OFF em cross-compilação; deixamos
# explícito para não depender de detecção no host de build.
WHISPER_CPP_CONF_OPTS = \
	-DGGML_NATIVE=OFF \
	-DWHISPER_BUILD_TESTS=OFF \
	-DWHISPER_BUILD_EXAMPLES=ON \
	-DWHISPER_BUILD_SERVER=OFF \
	-DWHISPER_SDL2=OFF \
	-DWHISPER_CURL=OFF \
	-DWHISPER_FATAL_WARNINGS=OFF

ifeq ($(BR2_TOOLCHAIN_HAS_LIBATOMIC),y)
WHISPER_CPP_CONF_OPTS += -DCMAKE_EXE_LINKER_FLAGS="-latomic"
endif

ifeq ($(BR2_PACKAGE_WHISPER_CPP_VULKAN),y)
# Shaders Vulkan são compilados com o glslc do HOST (Buildroot 2026.08 não
# empacota shaderc; o pacote llama-cpp tem a mesma exigência). O script
# scripts/build-iso.sh confere a presença do glslc antes de compilar.
WHISPER_CPP_DEPENDENCIES += vulkan-loader vulkan-headers
WHISPER_CPP_CONF_OPTS += -DGGML_VULKAN=ON
else
WHISPER_CPP_CONF_OPTS += -DGGML_VULKAN=OFF
endif

$(eval $(cmake-package))
