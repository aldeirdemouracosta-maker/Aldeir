include $(sort $(wildcard $(BR2_EXTERNAL_IA_MINIVIDEO_PATH)/package/*/*.mk))

# OpenBLAS sem Fortran no toolchain é compilado com ONLY_CBLAS=1: não existe o
# símbolo Fortran sgemm_, que o FindBLAS do CMake testa, e o llama.cpp falhava com
# "Could NOT find BLAS". O ggml só chama cblas_sgemm, que existe. Pré-definir o
# resultado do teste faz o CMake aceitar a libopenblas (que ele ainda procura e linka).
ifeq ($(BR2_PACKAGE_OPENBLAS)$(BR2_PACKAGE_LLAMA_CPP),yy)
LLAMA_CPP_CONF_OPTS += -DBLAS_openblas_WORKS=ON
endif

# libfm e pcmanfm 1.3.2 não compilam com o GCC 15 do toolchain: C23 passou a ser o
# padrão e ponteiros incompatíveis viraram erro (código gerado pelo Vala e casts
# de GObject; ex.: action.c "assignment to 'gchar **' from 'const gchar * const*'").
# O código é C17 válido com avisos: compila como gnu17 e mantém o aviso.
LIBFM_CONF_ENV += CFLAGS="$(TARGET_CFLAGS) -std=gnu17 -Wno-error=incompatible-pointer-types"
PCMANFM_CONF_ENV += CFLAGS="$(TARGET_CFLAGS) -std=gnu17 -Wno-error=incompatible-pointer-types"
