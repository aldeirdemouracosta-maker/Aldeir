#pragma once
#include <cstddef>
#include <cstdint>

namespace vm {

enum class FxPreset : int { None = 0, Hero = 1, Energy = 2, Cosmic = 3, Noir = 4 };

struct FxParams {
    float shadow[3] = {0, 0, 0};     // deslocamento de cor aplicado nas sombras
    float highlight[3] = {0, 0, 0};  // idem nas luzes
    float contrast = 0;              // 0..1
    float saturation = 0;            // -1..1
    float bloom = 0;                 // intensidade do brilho (screen)
    float bloom_threshold = 0.7f;
    float chroma = 0;                // aberração cromática, fração da largura
    float vignette = 0;
    float grain = 0;
    bool red_isolate = false;        // só o vermelho mantém cor
    bool is_identity() const;
};

FxParams params_for(FxPreset preset, float intensity);

// RGBA_8888 em memória (R,G,B,A), alfa preservado.
void apply_fx(std::uint8_t* rgba, int w, int h, int stride_bytes,
              const FxParams& p, std::uint32_t seed);

// Fantasma monocromático para onion skin. tint = 0xRRGGBB.
void onion_ghost(std::uint8_t* rgba, int w, int h, int stride_bytes,
                 std::uint32_t tint, float strength);

struct Plane {
    std::uint8_t* data;
    int row_stride;
    int pixel_stride;
    std::size_t capacity;
};

// RGBA -> YUV 4:2:0 (BT.709, faixa limitada) em planos com strides arbitrários
// (NV12, I420...). Retorna false se algum plano não comportar a imagem.
bool rgba_to_yuv420(const std::uint8_t* rgba, int w, int h, int stride_bytes,
                    const Plane& y, const Plane& u, const Plane& v);

} // namespace vm
