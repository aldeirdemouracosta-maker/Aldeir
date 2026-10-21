#include "vm/face_swap.hpp"

#include <algorithm>
#include <cmath>
#include <cstring>

namespace vm {
namespace {

// Subconjunto usado (índices do MediaPipe face mesh): contorno, olhos, sobrancelhas, nariz, lábios, bochechas.
// Os índices só precisam ser os mesmos na foto e no quadro: a correspondência é automática.
const int kOval[] = {10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365, 379, 378, 400, 377, 152, 148,
                     176, 149, 150, 136, 172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109};
const int kInner[] = {
    263, 249, 390, 373, 374, 380, 381, 382, 362, 466, 388, 387, 386, 385, 384, 398,          // olho esquerdo
    33, 7, 163, 144, 145, 153, 154, 155, 133, 246, 161, 160, 159, 158, 157, 173,             // olho direito
    276, 283, 282, 295, 285, 300, 293, 334, 296, 336, 46, 53, 52, 65, 55, 70, 63, 105, 66, 107,  // sobrancelhas
    61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291, 185, 40, 39, 37, 0, 267, 269, 270, 409,   // lábio externo
    78, 95, 88, 178, 87, 14, 317, 402, 318, 324, 308, 191, 80, 81, 82, 13, 312, 311, 310, 415,   // lábio interno
    1, 2, 4, 5, 6, 19, 94, 168, 195, 197, 98, 327, 129, 358, 48, 278,                         // nariz
    50, 280, 205, 425, 187, 411, 116, 345, 117, 346, 123, 352};                              // bochechas

constexpr int kOvalN = static_cast<int>(sizeof(kOval) / sizeof(kOval[0]));

const std::vector<int>& subset() {
    static const std::vector<int> idx = [] {
        std::vector<int> v(kOval, kOval + kOvalN);
        for (int i : kInner)
            if (std::find(v.begin(), v.end(), i) == v.end()) v.push_back(i);
        return v;
    }();
    return idx;
}

inline float clampf(float v, float lo, float hi) { return v < lo ? lo : (v > hi ? hi : v); }

bool finite_pts(const float* xy, int count) {
    if (!xy || count < kFaceLandmarks * 2) return false;
    for (int i = 0; i < kFaceLandmarks * 2; ++i)
        if (!std::isfinite(xy[i])) return false;
    return true;
}

std::vector<Pt> pick(const float* xy) {
    std::vector<Pt> p;
    for (int i : subset()) p.push_back({xy[i * 2], xy[i * 2 + 1]});
    return p;
}

float poly_area(const std::vector<Pt>& p) {
    double a = 0;
    for (std::size_t i = 0; i < p.size(); ++i) {
        const Pt &u = p[i], &v = p[(i + 1) % p.size()];
        a += static_cast<double>(u.x) * v.y - static_cast<double>(v.x) * u.y;
    }
    return static_cast<float>(std::fabs(a) * 0.5);
}

bool inside_poly(const std::vector<Pt>& p, float x, float y) {
    bool in = false;
    for (std::size_t i = 0, j = p.size() - 1; i < p.size(); j = i++) {
        if (((p[i].y > y) != (p[j].y > y)) && (x < (p[j].x - p[i].x) * (y - p[i].y) / (p[j].y - p[i].y) + p[i].x)) in = !in;
    }
    return in;
}

float dist_to_edges(const std::vector<Pt>& p, float x, float y) {
    float best = 1e30f;
    for (std::size_t i = 0; i < p.size(); ++i) {
        const Pt &a = p[i], &b = p[(i + 1) % p.size()];
        const float vx = b.x - a.x, vy = b.y - a.y;
        const float l2 = vx * vx + vy * vy;
        float t = l2 > 0 ? ((x - a.x) * vx + (y - a.y) * vy) / l2 : 0.f;
        t = clampf(t, 0.f, 1.f);
        const float dx = x - (a.x + t * vx), dy = y - (a.y + t * vy);
        best = std::min(best, dx * dx + dy * dy);
    }
    return std::sqrt(best);
}

void sample_bilinear(const std::uint8_t* img, int w, int h, int stride, float x, float y, float out[3]) {
    x = clampf(x, 0.f, static_cast<float>(w - 1));
    y = clampf(y, 0.f, static_cast<float>(h - 1));
    const int x0 = static_cast<int>(x), y0 = static_cast<int>(y);
    const int x1 = std::min(x0 + 1, w - 1), y1 = std::min(y0 + 1, h - 1);
    const float fx = x - static_cast<float>(x0), fy = y - static_cast<float>(y0);
    for (int c = 0; c < 3; ++c) {
        const float a = img[static_cast<std::size_t>(y0) * stride + x0 * 4 + c], b = img[static_cast<std::size_t>(y0) * stride + x1 * 4 + c];
        const float d = img[static_cast<std::size_t>(y1) * stride + x0 * 4 + c], e = img[static_cast<std::size_t>(y1) * stride + x1 * 4 + c];
        out[c] = (a * (1 - fx) + b * fx) * (1 - fy) + (d * (1 - fx) + e * fx) * fy;
    }
}

} // namespace

int face_oval_count() { return kOvalN; }
const int* face_oval_indices() { return kOval; }

// --------------------------------------------------------------------------- Delaunay
std::vector<Tri> delaunay(const std::vector<Pt>& pts) {
    const int n = static_cast<int>(pts.size());
    if (n < 3) return {};
    struct T { int a, b, c; double cx, cy, r2; bool bad; };
    std::vector<std::pair<double, double>> p;
    p.reserve(static_cast<std::size_t>(n) + 3);
    double minx = 1e300, miny = 1e300, maxx = -1e300, maxy = -1e300;
    for (const Pt& q : pts) {
        if (!std::isfinite(q.x) || !std::isfinite(q.y)) return {};
        p.push_back({q.x, q.y});
        minx = std::min<double>(minx, q.x); maxx = std::max<double>(maxx, q.x);
        miny = std::min<double>(miny, q.y); maxy = std::max<double>(maxy, q.y);
    }
    const double d = std::max(maxx - minx, maxy - miny);
    if (d <= 0) return {};
    const double mx = (minx + maxx) / 2, my = (miny + maxy) / 2;
    p.push_back({mx - 20 * d, my - d});
    p.push_back({mx, my + 20 * d});
    p.push_back({mx + 20 * d, my - d});

    auto make = [&](int a, int b, int c) {
        T t{a, b, c, 0, 0, 0, false};
        const double ax = p[a].first, ay = p[a].second, bx = p[b].first, by = p[b].second, cx = p[c].first, cy = p[c].second;
        const double dd = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by));
        if (std::fabs(dd) < 1e-12) { t.r2 = -1; return t; }
        t.cx = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay) + (cx * cx + cy * cy) * (ay - by)) / dd;
        t.cy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx) + (cx * cx + cy * cy) * (bx - ax)) / dd;
        t.r2 = (ax - t.cx) * (ax - t.cx) + (ay - t.cy) * (ay - t.cy);
        return t;
    };

    std::vector<T> tris;
    tris.push_back(make(n, n + 1, n + 2));
    for (int i = 0; i < n; ++i) {
        const double px = p[i].first, py = p[i].second;
        std::vector<std::pair<int, int>> edges;
        for (T& t : tris) {
            if (t.r2 < 0) { t.bad = true; continue; }
            const double dx = px - t.cx, dy = py - t.cy;
            t.bad = dx * dx + dy * dy < t.r2 * (1 - 1e-12);
        }
        for (const T& t : tris) {
            if (!t.bad) continue;
            const int e[3][2] = {{t.a, t.b}, {t.b, t.c}, {t.c, t.a}};
            for (auto& ed : e) {
                bool shared = false;
                for (const T& o : tris) {
                    if (&o == &t || !o.bad) continue;
                    const int f[3][2] = {{o.a, o.b}, {o.b, o.c}, {o.c, o.a}};
                    for (auto& fe : f)
                        if ((fe[0] == ed[0] && fe[1] == ed[1]) || (fe[0] == ed[1] && fe[1] == ed[0])) shared = true;
                }
                if (!shared) edges.push_back({ed[0], ed[1]});
            }
        }
        tris.erase(std::remove_if(tris.begin(), tris.end(), [](const T& t) { return t.bad; }), tris.end());
        for (auto& e : edges) {
            T t = make(e.first, e.second, i);
            if (t.r2 >= 0) tris.push_back(t);
        }
    }
    std::vector<Tri> out;
    for (const T& t : tris)
        if (t.a < n && t.b < n && t.c < n) out.push_back({t.a, t.b, t.c});
    return out;
}

// --------------------------------------------------------------------------- suavização
void LandmarkSmoother::filter(float* xy, int count, double t) {
    if (!xy || count <= 0) return;
    if (!have_ || x_.size() != static_cast<std::size_t>(count)) {
        x_.assign(xy, xy + count);
        dx_.assign(static_cast<std::size_t>(count), 0.f);
        have_ = true;
        last_t_ = t;
        return;
    }
    double dt = t - last_t_;
    if (!(dt > 1e-4) || dt > 1.0) dt = 1.0 / 30.0;
    last_t_ = t;
    auto alpha = [&](float cutoff) {
        const double tau = 1.0 / (2.0 * 3.14159265358979 * static_cast<double>(cutoff));
        return static_cast<float>(1.0 / (1.0 + tau / dt));
    };
    const float ad = alpha(1.0f);
    for (int i = 0; i < count; ++i) {
        const float raw_d = static_cast<float>((xy[i] - x_[i]) / dt);
        dx_[i] += ad * (raw_d - dx_[i]);
        const float a = alpha(min_cutoff_ + beta_ * std::fabs(dx_[i]));
        x_[i] += a * (xy[i] - x_[i]);
        xy[i] = x_[i];
    }
}

// --------------------------------------------------------------------------- troca de rosto
bool FaceSwapper::init(const std::uint8_t* rgba, int w, int h, int stride, const float* xy, int count) {
    tris_.clear();
    if (!rgba || w < 32 || h < 32 || stride < w * 4 || w > 8192 || h > 8192 || !finite_pts(xy, count)) return false;
    std::vector<Pt> sp = pick(xy);
    std::vector<Pt> oval(sp.begin(), sp.begin() + kOvalN);
    if (poly_area(oval) < 400.f) return false;
    std::vector<Tri> t = delaunay(sp);
    if (t.empty()) return false;
    sw_ = w; sh_ = h;
    src_.resize(static_cast<std::size_t>(w) * h * 4);
    for (int y = 0; y < h; ++y) std::memcpy(&src_[static_cast<std::size_t>(y) * w * 4], rgba + static_cast<std::size_t>(y) * stride, static_cast<std::size_t>(w) * 4);
    sp_ = std::move(sp);
    tris_ = std::move(t);
    return true;
}

bool FaceSwapper::apply(std::uint8_t* px, int w, int h, int stride, const float* xy, int count, const SwapParams& prm) const {
    if (!ready() || !px || w < 16 || h < 16 || stride < w * 4 || !finite_pts(xy, count)) return false;
    const std::vector<Pt> dp = pick(xy);
    const std::vector<Pt> oval(dp.begin(), dp.begin() + kOvalN);
    float minx = 1e30f, miny = 1e30f, maxx = -1e30f, maxy = -1e30f;
    for (const Pt& q : oval) {
        minx = std::min(minx, q.x); maxx = std::max(maxx, q.x);
        miny = std::min(miny, q.y); maxy = std::max(maxy, q.y);
    }
    const float fw = maxx - minx;
    if (fw < 24.f || fw > 4.f * static_cast<float>(w) || poly_area(oval) < 300.f) return false;
    const int bx0 = std::max(0, static_cast<int>(std::floor(minx)) - 2), by0 = std::max(0, static_cast<int>(std::floor(miny)) - 2);
    const int bx1 = std::min(w - 1, static_cast<int>(std::ceil(maxx)) + 2), by1 = std::min(h - 1, static_cast<int>(std::ceil(maxy)) + 2);
    if (bx1 <= bx0 || by1 <= by0) return false;   // rosto totalmente fora do quadro
    const int bw = bx1 - bx0 + 1, bh = by1 - by0 + 1;

    // 1) rosto da foto deformado sobre a malha do quadro
    std::vector<float> layer(static_cast<std::size_t>(bw) * bh * 3, 0.f);
    std::vector<std::uint8_t> cov(static_cast<std::size_t>(bw) * bh, 0);
    for (const Tri& t : tris_) {
        const Pt &a = dp[t.a], &b = dp[t.b], &c = dp[t.c];
        const float den = (b.y - c.y) * (a.x - c.x) + (c.x - b.x) * (a.y - c.y);
        if (std::fabs(den) < 1e-6f) continue;
        const int x0 = std::max(bx0, static_cast<int>(std::floor(std::min({a.x, b.x, c.x})))), x1 = std::min(bx1, static_cast<int>(std::ceil(std::max({a.x, b.x, c.x}))));
        const int y0 = std::max(by0, static_cast<int>(std::floor(std::min({a.y, b.y, c.y})))), y1 = std::min(by1, static_cast<int>(std::ceil(std::max({a.y, b.y, c.y}))));
        const Pt &sa = sp_[t.a], &sb = sp_[t.b], &sc = sp_[t.c];
        for (int y = y0; y <= y1; ++y) {
            for (int x = x0; x <= x1; ++x) {
                const float fx = static_cast<float>(x) + 0.5f, fy = static_cast<float>(y) + 0.5f;
                const float l1 = ((b.y - c.y) * (fx - c.x) + (c.x - b.x) * (fy - c.y)) / den;
                const float l2 = ((c.y - a.y) * (fx - c.x) + (a.x - c.x) * (fy - c.y)) / den;
                const float l3 = 1.f - l1 - l2;
                if (l1 < -1e-3f || l2 < -1e-3f || l3 < -1e-3f) continue;
                float rgb[3];
                sample_bilinear(src_.data(), sw_, sh_, sw_ * 4, l1 * sa.x + l2 * sb.x + l3 * sc.x, l1 * sa.y + l2 * sb.y + l3 * sc.y, rgb);
                const std::size_t o = static_cast<std::size_t>(y - by0) * bw + (x - bx0);
                for (int k = 0; k < 3; ++k) layer[o * 3 + k] = rgb[k];
                cov[o] = 1;
            }
        }
    }

    // 2) máscara: distância à borda do contorno, suavizada
    const float feather = std::max(1.5f, prm.feather * fw);
    std::vector<float> mask(static_cast<std::size_t>(bw) * bh, 0.f);
    for (int y = by0; y <= by1; ++y) {
        for (int x = bx0; x <= bx1; ++x) {
            const std::size_t o = static_cast<std::size_t>(y - by0) * bw + (x - bx0);
            if (!cov[o]) continue;
            const float fx = static_cast<float>(x) + 0.5f, fy = static_cast<float>(y) + 0.5f;
            if (!inside_poly(oval, fx, fy)) continue;
            const float t = clampf(dist_to_edges(oval, fx, fy) / feather, 0.f, 1.f);
            mask[o] = t * t * (3.f - 2.f * t);
        }
    }

    // 3) correção de cor: média/desvio do rosto trocado igualados aos do rosto do vídeo
    if (prm.color_strength > 0.f) {
        double mt[3] = {0, 0, 0}, ml[3] = {0, 0, 0}, vt[3] = {0, 0, 0}, vl[3] = {0, 0, 0};
        long n = 0;
        for (int y = by0; y <= by1; y += 2) {
            for (int x = bx0; x <= bx1; x += 2) {
                const std::size_t o = static_cast<std::size_t>(y - by0) * bw + (x - bx0);
                if (mask[o] < 0.6f) continue;
                const std::uint8_t* s = px + static_cast<std::size_t>(y) * stride + x * 4;
                for (int k = 0; k < 3; ++k) {
                    const double a = s[k], b = layer[o * 3 + k];
                    mt[k] += a; ml[k] += b; vt[k] += a * a; vl[k] += b * b;
                }
                ++n;
            }
        }
        if (n > 40) {
            float gain[3];
            for (int k = 0; k < 3; ++k) {
                mt[k] /= n; ml[k] /= n;
                const double st = std::sqrt(std::max(0.0, vt[k] / n - mt[k] * mt[k])), sl = std::sqrt(std::max(0.0, vl[k] / n - ml[k] * ml[k]));
                const float g = clampf(sl > 2.0 ? static_cast<float>(st / sl) : 1.f, 0.6f, 1.6f);
                gain[k] = 1.f + (g - 1.f) * prm.color_strength;
            }
            for (std::size_t o = 0; o < static_cast<std::size_t>(bw) * bh; ++o) {
                if (!cov[o]) continue;
                for (int k = 0; k < 3; ++k)
                    layer[o * 3 + k] = (layer[o * 3 + k] - static_cast<float>(ml[k])) * gain[k] + static_cast<float>(ml[k]) +
                                       static_cast<float>(mt[k] - ml[k]) * prm.color_strength;
            }
        }
    }

    // 4) composição
    for (int y = by0; y <= by1; ++y) {
        for (int x = bx0; x <= bx1; ++x) {
            const std::size_t o = static_cast<std::size_t>(y - by0) * bw + (x - bx0);
            const float a = mask[o];
            if (a <= 0.f) continue;
            std::uint8_t* d = px + static_cast<std::size_t>(y) * stride + x * 4;
            for (int k = 0; k < 3; ++k) d[k] = static_cast<std::uint8_t>(clampf(d[k] * (1.f - a) + layer[o * 3 + k] * a, 0.f, 255.f) + 0.5f);
        }
    }
    return true;
}

} // namespace vm
