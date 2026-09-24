include $(sort $(wildcard $(BR2_EXTERNAL_IA_MINIVIDEO_PATH)/package/*/*.mk))

# OpenBLAS sem Fortran no toolchain é compilado com ONLY_CBLAS=1: não existe o
# símbolo Fortran sgemm_, que o FindBLAS do CMake testa, e o llama.cpp falhava com
# "Could NOT find BLAS". O ggml só chama cblas_sgemm, que existe. Pré-definir o
# resultado do teste faz o CMake aceitar a libopenblas (que ele ainda procura e linka).
ifeq ($(BR2_PACKAGE_OPENBLAS)$(BR2_PACKAGE_LLAMA_CPP),yy)
LLAMA_CPP_CONF_OPTS += -DBLAS_openblas_WORKS=ON
endif
