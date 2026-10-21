#include "vm/audio.hpp"
#include "vm/face_swap.hpp"
#include "vm/pixel_ops.hpp"
#include "vm/timeline.hpp"

#include <cstdio>
#include <cmath>
#include <algorithm>
#include <cstdlib>
#include <fstream>
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


static int peak(const vm::Pcm& p) { int m = 0; for (auto v : p) m = std::max(m, std::abs((int)v)); return m; }

static void audio_synth() {
    for (int i = 0; i < (int)Sfx::Count; ++i) {
        const Sfx s = (Sfx)i;
        Pcm a = synth(s), b = synth(s);
        CHECK(a == b);                                   // determinístico
        CHECK(a.size() > 4000 && a.size() < 3 * kAudioRate);
        CHECK(peak(a) > 20000 && peak(a) <= 32767);      // normalizado, sem estourar
        Sfx back; CHECK(sfx_from_name(sfx_name(s), back) && back == s);
        // não pode terminar com estalo: cauda quase silenciosa
        int tail = 0; for (size_t k = a.size() - 64; k < a.size(); ++k) tail = std::max(tail, std::abs((int)a[k]));
        CHECK(tail < 6000);
    }
    Sfx x; CHECK(!sfx_from_name("nada", x) && !sfx_from_name("", x));
}

static void audio_convert() {
    // 48 kHz estéreo -> 44,1 kHz mono
    std::vector<int16_t> st(48000 * 2);
    for (int i = 0; i < 48000; ++i) { st[2*i] = (int16_t)(8000 * std::sin(i * 0.05)); st[2*i+1] = st[2*i]; }
    Pcm m = to_mono_44k(st.data(), 48000, 48000, 2);
    CHECK(std::abs((int)m.size() - 44100) <= 2);
    CHECK(peak(m) > 7000 && peak(m) < 9000);
    // 22,05 kHz mono (ampliando)
    std::vector<int16_t> lo(22050, 1000);
    Pcm u = to_mono_44k(lo.data(), lo.size(), 22050, 1);
    CHECK(std::abs((int)u.size() - 44100) <= 2 && u[100] == 1000);
    CHECK(to_mono_44k(nullptr, 10, 44100, 1).empty());
    CHECK(to_mono_44k(lo.data(), 0, 44100, 1).empty());
    CHECK(to_mono_44k(lo.data(), 10, 100, 1).empty() && to_mono_44k(lo.data(), 10, 44100, 0).empty());
    // normalização não amplifica silêncio
    Pcm quiet(1000, 3); normalize_peak(quiet); CHECK(quiet[0] == 3);
    Pcm f(2000, 10000); fade_edges(f, 10); CHECK(f[0] == 0 && f[1000] == 10000 && std::abs(f.back()) < 200);
}

static void audio_wav() {
    const char* path = "/tmp/vm_core_test.wav";
    Pcm src = synth(Sfx::Laser);
    CHECK(write_wav(path, src));
    std::vector<int16_t> back; int rate = 0, ch = 0;
    CHECK(read_wav(path, back, rate, ch) && rate == kAudioRate && ch == 1 && back == src);
    // importação limita a duração e converte
    Pcm longclip(kAudioRate * 12, 0);
    for (size_t i = 0; i < longclip.size(); ++i) longclip[i] = (int16_t)(6000 * std::sin(i * 0.03));
    CHECK(write_wav("/tmp/vm_core_long.wav", longclip));
    CHECK(import_wav("/tmp/vm_core_long.wav", "/tmp/vm_core_imp.wav", 8000));
    CHECK(read_wav("/tmp/vm_core_imp.wav", back, rate, ch) && back.size() == (size_t)kAudioRate * 8 && peak(back) > 28000);
    // arquivos inválidos
    { std::ofstream o("/tmp/vm_core_bad.wav", std::ios::binary); o << "isto nao e um wav, bem maior que 44 bytes................."; }
    CHECK(!read_wav("/tmp/vm_core_bad.wav", back, rate, ch) && !import_wav("/tmp/vm_core_bad.wav", "/tmp/x.wav"));
    CHECK(!read_wav("/tmp/nao_existe_vm.wav", back, rate, ch));
    { // cabeçalho válido, dados truncados/sem amostras
      std::ifstream i(path, std::ios::binary); std::string all((std::istreambuf_iterator<char>(i)), std::istreambuf_iterator<char>());
      { std::ofstream o("/tmp/vm_core_trunc.wav", std::ios::binary); o.write(all.data(), 44); }
      CHECK(!read_wav("/tmp/vm_core_trunc.wav", back, rate, ch));
      { std::ofstream o("/tmp/vm_core_trunc2.wav", std::ios::binary); o.write(all.data(), 44 + 2001); }   // metade de uma amostra sobra
      CHECK(read_wav("/tmp/vm_core_trunc2.wav", back, rate, ch) && back.size() == 1000);
    }
}

static void audio_timeline_and_mix() {
    AudioTimeline t;
    CHECK(t.add(2000000, 1000, "sfx:boom") && t.add(500000, 500, "sfx:laser") && t.add(0, 1000, "file:voz_1.wav"));
    CHECK(t.size() == 3 && t.at(0)->start_us == 0 && t.at(2)->start_us == 2000000);   // ordenado
    CHECK(!t.add(0, 1000, "sfx:nope") && !t.add(0, 1000, "file:../x.wav") && !t.add(0, 1000, "arquivo") && !t.add(-5, 1000, "sfx:boom"));
    CHECK(t.add(0, 99999, "sfx:glass"));
    size_t gi = 99; for (size_t i = 0; i < t.size(); ++i) if (t.at(i)->source == "sfx:glass") gi = i;
    CHECK(gi < t.size() && t.at(gi)->gain_milli == AudioTimeline::kMaxGain);
    CHECK(t.set_gain(gi, -4) && t.at(gi)->gain_milli == 0 && !t.set_gain(99, 1));
    CHECK(t.remove(gi) && !t.remove(99) && t.size() == 3);
    const char* path = "/tmp/vm_core_test.vma";
    CHECK(t.save_atomic(path));
    AudioTimeline r; CHECK(r.load(path) && r.size() == t.size() && r.at(1)->source == t.at(1)->source);
    CHECK(!r.parse("lixo") && !r.parse("VMA1\nevent 0 1000 sfx:nope\n") && !r.parse("VMA1\nevent -1 1000 sfx:boom\n") && !r.parse("VMA1\nevent 0 9999999 sfx:boom\n"));
    CHECK(r.size() == t.size());

    // mixagem: silêncio antes do evento, som depois, blocos consistentes
    AudioEngine e("/tmp");
    e.timeline().add(1000000, 1000, "sfx:gunshot");              // começa em 1,0 s
    std::vector<int16_t> whole(kAudioRate * 2), part(1000);
    e.render(0, whole.size(), whole.data());
    bool silent = true; for (int i = 0; i < kAudioRate - 1; ++i) if (whole[i] != 0) silent = false;
    CHECK(silent);
    CHECK(peak(Pcm(whole.begin() + kAudioRate, whole.end())) > 20000);
    e.render(kAudioRate + 5000, part.size(), part.data());      // bloco no meio do evento == mesmo trecho da mixagem inteira
    CHECK(std::equal(part.begin(), part.end(), whole.begin() + kAudioRate + 5000));
    // ganho 0 = mudo; ganho alto nunca ultrapassa o limitador
    AudioEngine g("/tmp"); g.timeline().add(0, 0, "sfx:boom"); g.render(0, whole.size(), whole.data()); CHECK(peak(Pcm(whole.begin(), whole.end())) == 0);
    AudioEngine h("/tmp");
    for (int i = 0; i < 12; ++i) h.timeline().add(0, 3000, "sfx:explosion");
    h.render(0, whole.size(), whole.data()); CHECK(peak(Pcm(whole.begin(), whole.end())) <= 32767 * 0.98 + 1);
    // arquivo ausente é ignorado sem travar
    AudioEngine m("/tmp"); m.timeline().add(0, 1000, "file:nao_existe_vm.wav");
    m.render(0, whole.size(), whole.data()); CHECK(peak(Pcm(whole.begin(), whole.end())) == 0);
    CHECK(m.source_duration_us("file:nao_existe_vm.wav") == 0 && e.source_duration_us("sfx:gunshot") > 400000);
    // faixas fora do alcance e argumentos inválidos
    e.render(kAudioRate * 100, 100, part.data()); e.render(0, 0, part.data()); e.render(0, 10, nullptr);
}

// ---- troca de rosto: geometria testada com pontos sintéticos (sem modelo de ML)
static std::vector<float> fake_face(float cx, float cy, float scale, float ang, float jitter = 0.f) {
    std::vector<float> u(kFaceLandmarks * 2);
    unsigned s = 12345;
    for (int k = 0; k < kFaceLandmarks; ++k) {                      // interior: anéis até r = 0.8
        const float a = 6.2831853f * (k % 60) / 60.f, r = 0.2f + 0.6f * ((k / 60) % 8) / 7.f;
        u[2 * k] = 0.8f * r * std::cos(a); u[2 * k + 1] = r * std::sin(a);
    }
    for (int i = 0; i < face_oval_count(); ++i) {                   // contorno: elipse externa, em ordem
        const float a = 6.2831853f * i / face_oval_count();
        u[2 * face_oval_indices()[i]] = 0.8f * std::cos(a); u[2 * face_oval_indices()[i] + 1] = std::sin(a);
    }
    std::vector<float> xy(kFaceLandmarks * 2);
    for (int k = 0; k < kFaceLandmarks; ++k) {
        s = s * 1664525u + 1013904223u; float ux = u[2 * k] + jitter * ((s >> 16) / 65535.f - 0.5f);
        s = s * 1664525u + 1013904223u; float uy = u[2 * k + 1] + jitter * ((s >> 16) / 65535.f - 0.5f);
        xy[2 * k] = cx + scale * (ux * std::cos(ang) - uy * std::sin(ang));
        xy[2 * k + 1] = cy + scale * (ux * std::sin(ang) + uy * std::cos(ang));
    }
    return xy;
}

static void face_delaunay_smooth() {
    std::vector<Pt> pts;
    for (int i = 0; i < 7; ++i) for (int j = 0; j < 6; ++j) pts.push_back({i * 10.f + (j % 2) * 3.f + 0.7f * (i * j % 3), j * 9.f + 0.5f * (i % 2)});
    auto t = delaunay(pts);
    // área total dos triângulos = área do fecho convexo (cobertura sem buracos nem sobreposição)
    double sum = 0;
    for (auto& tr : t) { const Pt &a = pts[tr.a], &b = pts[tr.b], &c = pts[tr.c]; double ar = std::fabs((b.x - a.x) * (c.y - a.y) - (c.x - a.x) * (b.y - a.y)) / 2; CHECK(ar > 1e-6); sum += ar; }
    std::vector<Pt> h = pts; std::sort(h.begin(), h.end(), [](Pt p, Pt q) { return p.x < q.x || (p.x == q.x && p.y < q.y); });
    std::vector<Pt> hull(2 * h.size()); size_t k = 0;
    auto cross = [](Pt o, Pt a, Pt b) { return (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x); };
    for (size_t i = 0; i < h.size(); ++i) { while (k >= 2 && cross(hull[k-2], hull[k-1], h[i]) <= 0) --k; hull[k++] = h[i]; }
    for (size_t i = h.size() - 1, lo = k + 1; i > 0; --i) { while (k >= lo && cross(hull[k-2], hull[k-1], h[i-1]) <= 0) --k; hull[k++] = h[i-1]; }
    hull.resize(k - 1); double ha = 0; for (size_t i = 0; i < hull.size(); ++i) { Pt u = hull[i], v = hull[(i + 1) % hull.size()]; ha += u.x * v.y - v.x * u.y; }
    CHECK(std::fabs(sum - std::fabs(ha) / 2) < 0.01 * sum);
    CHECK(delaunay({}).empty() && delaunay({{0,0},{1,1}}).empty() && delaunay({{0,0},{1,1},{2,2},{3,3}}).empty());   // degenerados
    CHECK(delaunay({{0,0},{NAN,1},{2,2}}).empty());

    // suavizador: reduz tremor parado, segue salto rápido
    LandmarkSmoother sm; unsigned s = 7; double var_raw = 0, var_f = 0; int n = 0;
    for (int i = 0; i < 90; ++i) {
        s = s * 1664525u + 1013904223u; float noise = ((s >> 16) / 65535.f - 0.5f) * 6.f;
        float v[2] = {100 + noise, 200 + noise}; const float raw = v[0];
        sm.filter(v, 2, i / 30.0);
        if (i >= 20) { var_raw += (raw - 100) * (raw - 100); var_f += (v[0] - 100) * (v[0] - 100); ++n; }
    }
    CHECK(var_f < var_raw * 0.5);
    float jump[2] = {300, 400};
    for (int i = 0; i < 4; ++i) { jump[0] = 300; jump[1] = 400; sm.filter(jump, 2, (90 + i) / 30.0); }
    CHECK(std::fabs(jump[0] - 300) < 30);
    sm.reset(); float one[2] = {5, 6}; sm.filter(one, 2, 0); CHECK(one[0] == 5 && one[1] == 6);
}

static void face_swap_geometry() {
    // foto: cada pixel codifica sua posição (R = x, G = y)
    const int sw = 256, sh = 256, tw = 400, th = 400;
    std::vector<uint8_t> photo(sw * sh * 4), frame(tw * th * 4, 40);
    for (int y = 0; y < sh; ++y) for (int x = 0; x < sw; ++x) { auto* p = &photo[(y * sw + x) * 4]; p[0] = x; p[1] = y; p[2] = 128; p[3] = 255; }
    for (size_t i = 3; i < frame.size(); i += 4) frame[i] = 255;
    auto sp = fake_face(128, 128, 90, 0.f, 0.02f);
    FaceSwapper fs; CHECK(fs.init(photo.data(), sw, sh, sw * 4, sp.data(), (int)sp.size()));
    // alvo: o mesmo rosto escalado, girado e deslocado (semelhança): o mapeamento é conhecido
    const float scale = 130, ang = 0.35f, cx = 200, cy = 190;
    auto dp = fake_face(cx, cy, scale, ang, 0.02f);
    SwapParams prm; prm.color_strength = 0.f;
    auto out = frame;
    CHECK(fs.apply(out.data(), tw, th, tw * 4, dp.data(), (int)dp.size(), prm));
    // no centro do rosto a cor é a da foto no ponto inverso: confere R/G
    int ok = 0, tested = 0;
    for (int y = 150; y < 230; y += 5) for (int x = 160; x < 240; x += 5) {
        // inversa da semelhança: ponto da foto = centro_foto + R(-ang) * (p - centro_alvo) / escala * 90
        const float dx = (x + 0.5f - cx), dy = (y + 0.5f - cy);
        const float ux = (dx * std::cos(-ang) - dy * std::sin(-ang)) * 90.f / scale, uy = (dx * std::sin(-ang) + dy * std::cos(-ang)) * 90.f / scale;
        const float ex = 128 + ux, ey = 128 + uy;
        const uint8_t* o = &out[(y * tw + x) * 4];
        ++tested;
        if (std::fabs(o[0] - ex) < 6 && std::fabs(o[1] - ey) < 6) ++ok;
    }
    CHECK(ok > tested * 0.9);
    // fora do rosto o quadro permanece intacto; alfa preservado
    CHECK(out[(5 * tw + 5) * 4] == 40 && out[(390 * tw + 390) * 4 + 1] == 40);
    for (size_t i = 3; i < out.size(); i += 4) { if (out[i] != 255) { CHECK(false); break; } }

    // correção de cor: rosto da foto cinza-escuro sobre quadro claro fica mais claro, e força 0 não mexe
    std::vector<uint8_t> dark(sw * sh * 4, 60), bright(tw * th * 4, 200);
    for (size_t i = 3; i < dark.size(); i += 4) dark[i] = 255;
    for (size_t i = 3; i < bright.size(); i += 4) bright[i] = 255;
    FaceSwapper f2; CHECK(f2.init(dark.data(), sw, sh, sw * 4, sp.data(), (int)sp.size()));
    auto b1 = bright, b0 = bright; SwapParams full; full.color_strength = 1.f;
    CHECK(f2.apply(b1.data(), tw, th, tw * 4, dp.data(), (int)dp.size(), full));
    CHECK(f2.apply(b0.data(), tw, th, tw * 4, dp.data(), (int)dp.size(), prm));
    CHECK(b1[(190 * tw + 200) * 4] > 180);     // igualou a média do vídeo
    CHECK(b0[(190 * tw + 200) * 4] < 80);      // sem correção: continua escuro
    // bordas suaves: perto do contorno a mistura é parcial (nem foto pura, nem vídeo puro)
    int partial = 0; for (int x = 0; x < tw; ++x) { int v = b0[(190 * tw + x) * 4]; if (v > 70 && v < 190) ++partial; }
    CHECK(partial > 2);

    // entradas inválidas / rosto fora do quadro / minúsculo
    FaceSwapper bad; std::vector<float> few(100, 1.f);
    CHECK(!bad.init(photo.data(), sw, sh, sw * 4, few.data(), 100) && !bad.init(nullptr, sw, sh, sw * 4, sp.data(), (int)sp.size()));
    auto nanp = sp; nanp[10] = NAN; CHECK(!bad.init(photo.data(), sw, sh, sw * 4, nanp.data(), (int)nanp.size()));
    CHECK(!bad.apply(out.data(), tw, th, tw * 4, dp.data(), (int)dp.size()));           // sem init
    auto far = fake_face(-5000, -5000, 100, 0.f); auto c1 = frame; CHECK(!fs.apply(c1.data(), tw, th, tw * 4, far.data(), (int)far.size()) && c1 == frame);
    auto tiny = fake_face(200, 200, 8, 0.f); CHECK(!fs.apply(c1.data(), tw, th, tw * 4, tiny.data(), (int)tiny.size()));
    auto edge = fake_face(5, 5, 120, 0.f); CHECK(fs.apply(c1.data(), tw, th, tw * 4, edge.data(), (int)edge.size()));   // meio rosto cortado pelo canto: não pode estourar
    CHECK(!fs.apply(c1.data(), tw, th, tw * 2, dp.data(), (int)dp.size()));              // stride menor que a largura
}

int main() {
    timeline_ops(); timeline_io(); fx(); onion(); yuv(); audio_synth(); audio_convert(); audio_wav(); audio_timeline_and_mix(); face_delaunay_smooth(); face_swap_geometry();
    if (failures) { std::fprintf(stderr, "%d falha(s)\n", failures); return 1; }
    std::puts("core_tests: OK");
    return 0;
}
