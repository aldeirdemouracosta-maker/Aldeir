#include "vm/pixel_ops.hpp"
#include "vm/timeline.hpp"

#include <cstdio>
#include <cstdlib>
#include <vector>

static int failures = 0;
#define CHECK(c) do { if (!(c)) { std::fprintf(stderr, "FALHOU %s:%d  %s\n", __FILE__, __LINE__, #c); ++failures; } } while (0)

using namespace vm;

static void timeline_ops() {
    Timeline t(12);
    CHECK(t.add("a.jpg") && t.add("b.jpg", 3) && t.add("c.jpg"));
    CHECK(!t.add("../x.jpg") && !t.add("") && !t.add("a b.jpg") && !t.add("a\nb"));
    CHECK(t.size() == 3 && t.total_frames() == 5);
    CHECK(t.duration_us() == 5 * 1000000 / 12);
    CHECK(t.clip_at_time_us(0) == 0);
    CHECK(t.clip_at_time_us(1000000 / 12 + 1) == 1);   // frame 1 -> b
    CHECK(t.clip_at_time_us(3 * 1000000 / 12 + 10) == 1);
    CHECK(t.clip_at_time_us(4 * 1000000 / 12 + 10) == 2);
    CHECK(t.clip_at_time_us(t.duration_us()) == -1 && t.clip_at_time_us(-1) == -1);
    CHECK(t.duplicate(0) && t.size() == 4 && t.at(1)->file == "a.jpg");
    CHECK(t.references("a.jpg"));
    CHECK(t.remove(0) && t.references("a.jpg"));        // cópia ainda referencia
    CHECK(t.remove(0) && !t.references("a.jpg"));
    CHECK(t.move(0, 1) && t.at(0)->file == "c.jpg" && t.at(1)->file == "b.jpg");
    CHECK(!t.move(0, 9) && !t.remove(9) && !t.set_hold(9, 2) && !t.duplicate(9));
    CHECK(t.set_hold(0, 99999) && t.at(0)->hold == Timeline::kMaxHold);
    t.set_fps(0); CHECK(t.fps() == 1);
    t.set_fps(1000); CHECK(t.fps() == 60);
    Timeline empty; CHECK(empty.duration_us() == 0 && empty.clip_at_time_us(0) == -1);
}

static void timeline_io() {
    Timeline t(15);
    t.add("frame_000001.jpg", 2); t.add("frame_000002.jpg");
    const char* path = "/tmp/vm_core_test.vmt";
    CHECK(t.save_atomic(path));
    Timeline r;
    CHECK(r.load(path) && r.fps() == 15 && r.size() == 2 && r.at(0)->hold == 2);
    CHECK(!r.parse("lixo") && !r.parse("VMT1\nfps 12\nclip 1 ../../etc\n"));
    CHECK(!r.parse("VMT1\nfps 999\n") && !r.parse("VMT1\nclip 0 a.jpg\nfps 12\n"));
    CHECK(r.size() == 2);  // parse inválido não altera o estado
    CHECK(!r.load("/tmp/nao_existe_vm.vmt"));
    CHECK(!t.save_atomic("/tmp/nao/existe/dir/x.vmt"));
}

static std::vector<std::uint8_t> solid(int w, int h, int r, int g, int b) {
    std::vector<std::uint8_t> v(static_cast<size_t>(w) * h * 4);
    for (size_t i = 0; i < v.size(); i += 4) { v[i] = r; v[i+1] = g; v[i+2] = b; v[i+3] = 255; }
    return v;
}

static void fx() {
    const int w = 64, h = 48;
    auto img = solid(w, h, 120, 130, 140);
    auto orig = img;
    apply_fx(img.data(), w, h, w * 4, params_for(FxPreset::None, 1.f), 1);
    CHECK(img == orig);
    for (int p = 1; p <= 4; ++p) {
        auto a = orig, b = orig;
        apply_fx(a.data(), w, h, w * 4, params_for(static_cast<FxPreset>(p), 1.f), 7);
        apply_fx(b.data(), w, h, w * 4, params_for(static_cast<FxPreset>(p), 1.f), 7);
        CHECK(a == b);                       // determinístico
        CHECK(a != orig);
        for (size_t i = 3; i < a.size(); i += 4) CHECK(a[i] == 255);  // alfa intacto
    }
    // intensidade 0 = nada
    auto z = orig; apply_fx(z.data(), w, h, w * 4, params_for(FxPreset::Hero, 0.f), 1); CHECK(z == orig);
    // vinheta escurece o canto mais que o centro
    auto vg = solid(w, h, 200, 200, 200); FxParams vp; vp.vignette = 0.8f;
    apply_fx(vg.data(), w, h, w * 4, vp, 0);
    CHECK(vg[0] < vg[(h / 2 * w + w / 2) * 4]);
    // noir mantém vermelho e dessatura o resto
    auto red = solid(w, h, 220, 20, 20); auto blue = solid(w, h, 20, 20, 220);
    FxParams np; np.red_isolate = true;
    apply_fx(red.data(), w, h, w * 4, np, 0); apply_fx(blue.data(), w, h, w * 4, np, 0);
    CHECK(red[0] > 150 && red[1] < 60);
    CHECK(std::abs(blue[0] - blue[2]) < 6);
    // bloom: ponto brilhante ilumina vizinhos escuros
    auto dark = solid(w, h, 10, 10, 10);
    for (int dy = -1; dy <= 1; ++dy) for (int dx = -1; dx <= 1; ++dx) {
        auto* p = &dark[((h / 2 + dy) * w + (w / 2 + dx)) * 4]; p[0] = p[1] = p[2] = 255; }
    FxParams bp; bp.bloom = 1.f; apply_fx(dark.data(), w, h, w * 4, bp, 0);
    CHECK(dark[((h / 2) * w + (w / 2 + 6)) * 4] > 10);
    // stride maior que a largura (bitmaps com padding) não pode estourar
    std::vector<std::uint8_t> padded(static_cast<size_t>(h) * (w * 4 + 32), 100);
    apply_fx(padded.data(), w, h, w * 4 + 32, params_for(FxPreset::Energy, 1.f), 3);
    // argumentos inválidos
    apply_fx(nullptr, w, h, w * 4, params_for(FxPreset::Hero, 1.f), 0);
    apply_fx(img.data(), 0, h, w * 4, params_for(FxPreset::Hero, 1.f), 0);
    apply_fx(img.data(), w, h, w * 2, params_for(FxPreset::Hero, 1.f), 0);
    // imagem minúscula (1x1, 3x1)
    auto tiny = solid(1, 1, 200, 100, 50); apply_fx(tiny.data(), 1, 1, 4, params_for(FxPreset::Energy, 1.f), 0);
    auto thin = solid(3, 1, 200, 100, 50); apply_fx(thin.data(), 3, 1, 12, params_for(FxPreset::Cosmic, 1.f), 0);
}

static void onion() {
    auto img = solid(8, 8, 255, 0, 0);
    onion_ghost(img.data(), 8, 8, 32, 0x00E5FF, 1.f);
    CHECK(img[0] < 40 && img[2] > 100);   // tingido de ciano
    auto same = solid(8, 8, 10, 20, 30); auto o = same;
    onion_ghost(same.data(), 8, 8, 32, 0x00E5FF, 0.f);
    CHECK(same == o);
}

static void yuv() {
    const int w = 16, h = 8;
    struct Case { int r, g, b, y, u, v; } cases[] = {
        {255, 255, 255, 235, 128, 128}, {0, 0, 0, 16, 128, 128}, {255, 0, 0, 63, 102, 240}};
    for (auto& c : cases) {
        auto img = solid(w, h, c.r, c.g, c.b);
        // NV12: Y plano + UV intercalado
        std::vector<std::uint8_t> y(w * h), uv(w * h / 2);
        Plane py{y.data(), w, 1, y.size()}, pu{uv.data(), w, 2, uv.size()}, pv{uv.data() + 1, w, 2, uv.size() - 1};
        CHECK(rgba_to_yuv420(img.data(), w, h, w * 4, py, pu, pv));
        CHECK(std::abs(y[0] - c.y) <= 1);
        CHECK(std::abs(uv[0] - c.u) <= 2 && std::abs(uv[1] - c.v) <= 2);
        // I420 com strides maiores que a largura
        std::vector<std::uint8_t> y2(w * h + 64), u2(w * h / 4 + 64), v2(w * h / 4 + 64);
        Plane a{y2.data(), w + 8, 1, y2.size()}, b{u2.data(), w / 2 + 4, 1, u2.size()}, d{v2.data(), w / 2 + 4, 1, v2.size()};
        CHECK(rgba_to_yuv420(img.data(), w, h, w * 4, a, b, d));
        CHECK(std::abs(y2[0] - c.y) <= 1 && std::abs(u2[0] - c.u) <= 2 && std::abs(v2[0] - c.v) <= 2);
    }
    // plano pequeno demais é recusado em vez de estourar a memória
    auto img = solid(w, h, 9, 9, 9);
    std::vector<std::uint8_t> small(10);
    Plane ps{small.data(), w, 1, small.size()};
    CHECK(!rgba_to_yuv420(img.data(), w, h, w * 4, ps, ps, ps));
    // dimensões ímpares
    auto odd = solid(5, 3, 50, 60, 70);
    std::vector<std::uint8_t> oy(5 * 3), ou(3 * 2), ov(3 * 2);
    CHECK(rgba_to_yuv420(odd.data(), 5, 3, 20, {oy.data(), 5, 1, oy.size()}, {ou.data(), 3, 1, ou.size()}, {ov.data(), 3, 1, ov.size()}));
}

int main() {
    timeline_ops(); timeline_io(); fx(); onion(); yuv();
    if (failures) { std::fprintf(stderr, "%d falha(s)\n", failures); return 1; }
    std::puts("core_tests: OK");
    return 0;
}
