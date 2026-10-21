#include "vm/pixel_ops.hpp"

#include <algorithm>
#include <cmath>
#include <cstring>
#include <vector>

namespace vm {
namespace {

inline float clamp01(float v) { return v < 0.f ? 0.f : (v > 1.f ? 1.f : v); }

inline float smoothstep(float a, float b, float x) {
    const float t = clamp01((x - a) / (b - a));
    return t * t * (3.f - 2.f * t);
}

inline std::uint32_t hash32(std::uint32_t x, std::uint32_t y, std::uint32_t seed) {
    std::uint32_t h = x * 374761393u + y * 668265263u + seed * 2246822519u;
    h = (h ^ (h >> 13)) * 1274126177u;
    return h ^ (h >> 16);
}

constexpr int kBloomBlock = 4;

struct BloomMap {
    int w = 0, h = 0;
    std::vector<float> rgb;  // w*h*3
};

void box_blur_h(std::vector<float>& buf, std::vector<float>& tmp, int w, int h, int r) {
    const float inv = 1.f / static_cast<float>(2 * r + 1);
    for (int y = 0; y < h; ++y) {
        const float* src = &buf[static_cast<std::size_t>(y) * w * 3];
        float* dst = &tmp[static_cast<std::size_t>(y) * w * 3];
        for (int c = 0; c < 3; ++c) {
            float acc = 0;
            for (int k = -r; k <= r; ++k) acc += src[std::clamp(k, 0, w - 1) * 3 + c];
            dst[c] = acc * inv;
            for (int x = 1; x < w; ++x) {
                acc += src[std::min(x + r, w - 1) * 3 + c] - src[std::max(x - r - 1, 0) * 3 + c];
                dst[x * 3 + c] = acc * inv;
            }
        }
    }
}

void box_blur_v(std::vector<float>& buf, std::vector<float>& tmp, int w, int h, int r) {
    const float inv = 1.f / static_cast<float>(2 * r + 1);
    for (int x = 0; x < w; ++x) {
        for (int c = 0; c < 3; ++c) {
            float acc = 0;
            for (int k = -r; k <= r; ++k)
                acc += buf[(static_cast<std::size_t>(std::clamp(k, 0, h - 1)) * w + x) * 3 + c];
            tmp[(static_cast<std::size_t>(0) * w + x) * 3 + c] = acc * inv;
            for (int y = 1; y < h; ++y) {
                acc += buf[(static_cast<std::size_t>(std::min(y + r, h - 1)) * w + x) * 3 + c] -
                       buf[(static_cast<std::size_t>(std::max(y - r - 1, 0)) * w + x) * 3 + c];
                tmp[(static_cast<std::size_t>(y) * w + x) * 3 + c] = acc * inv;
            }
        }
    }
}

BloomMap build_bloom(const std::uint8_t* px, int w, int h, int stride, float threshold) {
    BloomMap m;
    m.w = (w + kBloomBlock - 1) / kBloomBlock;
    m.h = (h + kBloomBlock - 1) / kBloomBlock;
    m.rgb.assign(static_cast<std::size_t>(m.w) * m.h * 3, 0.f);
    const float denom = std::max(1e-3f, 1.f - threshold);
    for (int by = 0; by < m.h; ++by) {
        for (int bx = 0; bx < m.w; ++bx) {
            float acc[3] = {0, 0, 0};
            int n = 0;
            for (int y = by * kBloomBlock; y < std::min(h, (by + 1) * kBloomBlock); ++y) {
                const std::uint8_t* row = px + static_cast<std::size_t>(y) * stride;
                for (int x = bx * kBloomBlock; x < std::min(w, (bx + 1) * kBloomBlock); ++x) {
                    const float r = row[x * 4] / 255.f, g = row[x * 4 + 1] / 255.f, b = row[x * 4 + 2] / 255.f;
                    const float lum = 0.2126f * r + 0.7152f * g + 0.0722f * b;
                    const float k = std::max(0.f, (lum - threshold) / denom);
                    acc[0] += r * k; acc[1] += g * k; acc[2] += b * k;
                    ++n;
                }
            }
            float* o = &m.rgb[(static_cast<std::size_t>(by) * m.w + bx) * 3];
            for (int c = 0; c < 3; ++c) o[c] = n ? acc[c] / static_cast<float>(n) : 0.f;
        }
    }
    std::vector<float> tmp(m.rgb.size());
    for (int pass = 0; pass < 2; ++pass) {
        box_blur_h(m.rgb, tmp, m.w, m.h, 3);
        box_blur_v(tmp, m.rgb, m.w, m.h, 3);
    }
    return m;
}

inline void sample_bloom(const BloomMap& m, int x, int y, float out[3]) {
    const float fx = (static_cast<float>(x) + 0.5f) / kBloomBlock - 0.5f;
    const float fy = (static_cast<float>(y) + 0.5f) / kBloomBlock - 0.5f;
    const int x0 = static_cast<int>(std::floor(fx)), y0 = static_cast<int>(std::floor(fy));
    const float tx = fx - static_cast<float>(x0), ty = fy - static_cast<float>(y0);
    const int xa = std::clamp(x0, 0, m.w - 1), xb = std::clamp(x0 + 1, 0, m.w - 1);
    const int ya = std::clamp(y0, 0, m.h - 1), yb = std::clamp(y0 + 1, 0, m.h - 1);
    for (int c = 0; c < 3; ++c) {
        const float a = m.rgb[(static_cast<std::size_t>(ya) * m.w + xa) * 3 + c];
        const float b = m.rgb[(static_cast<std::size_t>(ya) * m.w + xb) * 3 + c];
        const float d = m.rgb[(static_cast<std::size_t>(yb) * m.w + xa) * 3 + c];
        const float e = m.rgb[(static_cast<std::size_t>(yb) * m.w + xb) * 3 + c];
        out[c] = (a * (1 - tx) + b * tx) * (1 - ty) + (d * (1 - tx) + e * tx) * ty;
    }
}

} // namespace

bool FxParams::is_identity() const {
    for (int i = 0; i < 3; ++i)
        if (shadow[i] != 0 || highlight[i] != 0) return false;
    return contrast == 0 && saturation == 0 && bloom == 0 && chroma == 0 &&
           vignette == 0 && grain == 0 && !red_isolate;
}

FxParams params_for(FxPreset preset, float intensity) {
    const float k = clamp01(intensity);
    FxParams p;
    switch (preset) {
        case FxPreset::Hero:  // teal & orange de cinema + vinheta
            p.shadow[0] = -0.05f; p.shadow[1] = 0.02f; p.shadow[2] = 0.08f;
            p.highlight[0] = 0.09f; p.highlight[1] = 0.03f; p.highlight[2] = -0.08f;
            p.contrast = 0.22f; p.saturation = 0.15f; p.bloom = 0.25f;
            p.vignette = 0.35f; p.grain = 0.02f;
            break;
        case FxPreset::Energy:  // explosão de energia: brilho forte + cromática
            p.shadow[0] = -0.02f; p.shadow[2] = 0.05f;
            p.highlight[0] = 0.07f; p.highlight[1] = 0.04f; p.highlight[2] = -0.02f;
            p.contrast = 0.30f; p.saturation = 0.30f; p.bloom = 0.85f;
            p.bloom_threshold = 0.55f; p.chroma = 0.006f; p.vignette = 0.25f;
            break;
        case FxPreset::Cosmic:  // roxo/magenta cósmico
            p.shadow[0] = 0.06f; p.shadow[1] = -0.04f; p.shadow[2] = 0.13f;
            p.highlight[0] = 0.11f; p.highlight[1] = -0.02f; p.highlight[2] = 0.07f;
            p.contrast = 0.18f; p.saturation = 0.20f; p.bloom = 0.55f;
            p.bloom_threshold = 0.6f; p.chroma = 0.003f; p.vignette = 0.40f; p.grain = 0.04f;
            break;
        case FxPreset::Noir:  // preto e branco com vermelho isolado
            p.red_isolate = true; p.contrast = 0.35f; p.vignette = 0.45f; p.grain = 0.05f;
            break;
        case FxPreset::None:
        default:
            return p;
    }
    for (float& v : p.shadow) v *= k;
    for (float& v : p.highlight) v *= k;
    p.contrast *= k; p.saturation *= k; p.bloom *= k; p.chroma *= k;
    p.vignette *= k; p.grain *= k;
    if (preset == FxPreset::Noir && k <= 0.f) p.red_isolate = false;
    return p;
}

void apply_fx(std::uint8_t* px, int w, int h, int stride, const FxParams& p, std::uint32_t seed) {
    if (!px || w <= 0 || h <= 0 || stride < w * 4 || p.is_identity()) return;

    const float cx = (static_cast<float>(w) - 1.f) * 0.5f, cy = (static_cast<float>(h) - 1.f) * 0.5f;
    const float icx = cx > 0 ? 1.f / cx : 0.f, icy = cy > 0 ? 1.f / cy : 0.f;

    if (p.chroma > 0.f) {
        const int max_shift = std::max(1, static_cast<int>(std::lround(p.chroma * static_cast<float>(w))));
        std::vector<std::uint8_t> row(static_cast<std::size_t>(w) * 4);
        for (int y = 0; y < h; ++y) {
            std::uint8_t* d = px + static_cast<std::size_t>(y) * stride;
            std::memcpy(row.data(), d, row.size());
            for (int x = 0; x < w; ++x) {
                const int s = static_cast<int>(std::lround((static_cast<float>(x) - cx) * icx * static_cast<float>(max_shift)));
                d[x * 4] = row[static_cast<std::size_t>(std::clamp(x + s, 0, w - 1)) * 4];
                d[x * 4 + 2] = row[static_cast<std::size_t>(std::clamp(x - s, 0, w - 1)) * 4 + 2];
            }
        }
    }

    BloomMap bloom;
    const bool use_bloom = p.bloom > 0.f;
    if (use_bloom) bloom = build_bloom(px, w, h, stride, p.bloom_threshold);

    for (int y = 0; y < h; ++y) {
        std::uint8_t* d = px + static_cast<std::size_t>(y) * stride;
        const float ny = (static_cast<float>(y) - cy) * icy;
        for (int x = 0; x < w; ++x) {
            float r = d[x * 4] / 255.f, g = d[x * 4 + 1] / 255.f, b = d[x * 4 + 2] / 255.f;

            if (use_bloom) {
                float bl[3];
                sample_bloom(bloom, x, y, bl);
                r = 1.f - (1.f - r) * (1.f - clamp01(bl[0] * p.bloom));
                g = 1.f - (1.f - g) * (1.f - clamp01(bl[1] * p.bloom));
                b = 1.f - (1.f - b) * (1.f - clamp01(bl[2] * p.bloom));
            }

            float lum = 0.2126f * r + 0.7152f * g + 0.0722f * b;
            const float sh = (1.f - lum) * (1.f - lum), hi = lum * lum;
            r += sh * p.shadow[0] + hi * p.highlight[0];
            g += sh * p.shadow[1] + hi * p.highlight[1];
            b += sh * p.shadow[2] + hi * p.highlight[2];

            if (p.contrast != 0.f) {
                const float c = 1.f + p.contrast;
                r = (r - 0.5f) * c + 0.5f; g = (g - 0.5f) * c + 0.5f; b = (b - 0.5f) * c + 0.5f;
            }
            lum = 0.2126f * r + 0.7152f * g + 0.0722f * b;
            if (p.saturation != 0.f) {
                const float s = 1.f + p.saturation;
                r = lum + (r - lum) * s; g = lum + (g - lum) * s; b = lum + (b - lum) * s;
            }
            if (p.red_isolate) {
                const float red = (r - std::max(g, b));
                const float keep = smoothstep(0.12f, 0.30f, red);
                r = lum + (r - lum) * keep; g = lum + (g - lum) * keep; b = lum + (b - lum) * keep;
            }

            if (p.vignette > 0.f) {
                const float nx = (static_cast<float>(x) - cx) * icx;
                const float dist = std::sqrt((nx * nx + ny * ny) * 0.5f);
                const float v = 1.f - p.vignette * smoothstep(0.35f, 1.0f, dist);
                r *= v; g *= v; b *= v;
            }
            if (p.grain > 0.f) {
                const float n = (static_cast<float>(hash32(static_cast<std::uint32_t>(x), static_cast<std::uint32_t>(y), seed) & 0xffff) / 65535.f - 0.5f) * p.grain;
                r += n; g += n; b += n;
            }

            d[x * 4] = static_cast<std::uint8_t>(clamp01(r) * 255.f + 0.5f);
            d[x * 4 + 1] = static_cast<std::uint8_t>(clamp01(g) * 255.f + 0.5f);
            d[x * 4 + 2] = static_cast<std::uint8_t>(clamp01(b) * 255.f + 0.5f);
        }
    }
}

void onion_ghost(std::uint8_t* px, int w, int h, int stride, std::uint32_t tint, float strength) {
    if (!px || w <= 0 || h <= 0 || stride < w * 4) return;
    const float s = clamp01(strength);
    const float tr = static_cast<float>((tint >> 16) & 0xff), tg = static_cast<float>((tint >> 8) & 0xff),
                tb = static_cast<float>(tint & 0xff);
    for (int y = 0; y < h; ++y) {
        std::uint8_t* d = px + static_cast<std::size_t>(y) * stride;
        for (int x = 0; x < w; ++x) {
            const float lum = (0.2126f * d[x * 4] + 0.7152f * d[x * 4 + 1] + 0.0722f * d[x * 4 + 2]) / 255.f;
            const float k = 0.35f + 0.65f * lum;
            const float gr = tr * k, gg = tg * k, gb = tb * k;
            d[x * 4] = static_cast<std::uint8_t>(std::min(255.f, d[x * 4] * (1 - s) + gr * s + 0.5f));
            d[x * 4 + 1] = static_cast<std::uint8_t>(std::min(255.f, d[x * 4 + 1] * (1 - s) + gg * s + 0.5f));
            d[x * 4 + 2] = static_cast<std::uint8_t>(std::min(255.f, d[x * 4 + 2] * (1 - s) + gb * s + 0.5f));
        }
    }
}

namespace {
bool plane_fits(const Plane& pl, int pw, int ph) {
    if (!pl.data || pw <= 0 || ph <= 0 || pl.row_stride < 1 || pl.pixel_stride < 1) return false;
    const std::size_t last = static_cast<std::size_t>(ph - 1) * pl.row_stride +
                             static_cast<std::size_t>(pw - 1) * pl.pixel_stride;
    return last < pl.capacity;
}
} // namespace

bool rgba_to_yuv420(const std::uint8_t* rgba, int w, int h, int stride,
                    const Plane& y, const Plane& u, const Plane& v) {
    if (!rgba || w <= 0 || h <= 0 || stride < w * 4) return false;
    const int cw = (w + 1) / 2, ch = (h + 1) / 2;
    if (!plane_fits(y, w, h) || !plane_fits(u, cw, ch) || !plane_fits(v, cw, ch)) return false;

    for (int j = 0; j < h; ++j) {
        const std::uint8_t* s = rgba + static_cast<std::size_t>(j) * stride;
        std::uint8_t* d = y.data + static_cast<std::size_t>(j) * y.row_stride;
        for (int i = 0; i < w; ++i, s += 4, d += y.pixel_stride)
            *d = static_cast<std::uint8_t>(16 + ((47 * s[0] + 157 * s[1] + 16 * s[2] + 128) >> 8));
    }
    for (int j = 0; j < ch; ++j) {
        const int y0 = j * 2, y1 = std::min(y0 + 1, h - 1);
        const std::uint8_t* r0 = rgba + static_cast<std::size_t>(y0) * stride;
        const std::uint8_t* r1 = rgba + static_cast<std::size_t>(y1) * stride;
        std::uint8_t* du = u.data + static_cast<std::size_t>(j) * u.row_stride;
        std::uint8_t* dv = v.data + static_cast<std::size_t>(j) * v.row_stride;
        for (int i = 0; i < cw; ++i, du += u.pixel_stride, dv += v.pixel_stride) {
            const int x0 = i * 2, x1 = std::min(x0 + 1, w - 1);
            int r = 0, g = 0, b = 0;
            for (const std::uint8_t* p : {r0 + x0 * 4, r0 + x1 * 4, r1 + x0 * 4, r1 + x1 * 4}) {
                r += p[0]; g += p[1]; b += p[2];
            }
            r = (r + 2) >> 2; g = (g + 2) >> 2; b = (b + 2) >> 2;
            *du = static_cast<std::uint8_t>(std::clamp(128 + ((-26 * r - 86 * g + 112 * b + 128) >> 8), 0, 255));
            *dv = static_cast<std::uint8_t>(std::clamp(128 + ((112 * r - 102 * g - 10 * b + 128) >> 8), 0, 255));
        }
    }
    return true;
}

} // namespace vm
