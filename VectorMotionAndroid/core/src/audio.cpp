#include "vm/audio.hpp"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <sstream>
#include <unistd.h>

#include "vm/timeline.hpp"

namespace vm {
namespace {

constexpr double kPi = 3.14159265358979323846;
constexpr float kSr = static_cast<float>(kAudioRate);

// Ruído branco determinístico (LCG) para que o mesmo SFX saia idêntico sempre.
struct Rng {
    std::uint32_t s;
    explicit Rng(std::uint32_t seed) : s(seed) {}
    float next() {  // [-1, 1)
        s = s * 1664525u + 1013904223u;
        return static_cast<float>(static_cast<std::int32_t>(s)) / 2147483648.f;
    }
};

struct OnePole {
    float y = 0;
    float lp(float x, float fc) {
        const float a = 1.f - std::exp(-2.f * static_cast<float>(kPi) * fc / kSr);
        y += a * (x - y);
        return y;
    }
};

// Filtro de variáveis de estado (Chamberlin): passa-banda/baixa.
struct Svf {
    float low = 0, band = 0;
    void run(float x, float fc, float q, float& lo, float& bp, float& hp) {
        const float f = 2.f * std::sin(static_cast<float>(kPi) * std::min(fc, 0.45f * kSr) / kSr);
        low += f * band;
        hp = x - low - q * band;
        band += f * hp;
        lo = low; bp = band;
    }
};

inline float expdec(float t, float tau) { return std::exp(-t / tau); }

Pcm to_pcm(const std::vector<float>& f) {
    Pcm p(f.size());
    for (std::size_t i = 0; i < f.size(); ++i) {
        const float v = std::max(-1.f, std::min(1.f, f[i]));
        p[i] = static_cast<std::int16_t>(std::lrintf(v * 32767.f));
    }
    return p;
}

std::vector<float> make(float seconds) { return std::vector<float>(static_cast<std::size_t>(seconds * kSr), 0.f); }

void norm(std::vector<float>& f, float target = 0.9f) {
    float peak = 0;
    for (float v : f) peak = std::max(peak, std::fabs(v));
    if (peak < 1e-6f) return;
    const float k = target / peak;
    for (float& v : f) v *= k;
}

std::vector<float> s_explosion() {
    auto o = make(1.6f);
    Rng r(1); OnePole lpf; float ph = 0;
    for (std::size_t i = 0; i < o.size(); ++i) {
        const float t = static_cast<float>(i) / kSr;
        const float fc = 200.f + 5800.f * expdec(t, 0.18f);
        float n = lpf.lp(r.next(), fc) * expdec(t, 0.45f);
        ph += 2.f * static_cast<float>(kPi) * (30.f + 28.f * expdec(t, 0.12f)) / kSr;
        const float sub = std::sin(ph) * expdec(t, 0.35f);
        const float crack = t < 0.006f ? r.next() * (1.f - t / 0.006f) : 0.f;
        o[i] = 1.4f * n + 0.9f * sub + crack;
    }
    for (float& v : o) v = std::tanh(1.6f * v);
    norm(o); return o;
}

std::vector<float> s_gunshot() {
    auto o = make(0.55f);
    Rng r(2); OnePole hp, tail; float ph = 0, prev = 0;
    for (std::size_t i = 0; i < o.size(); ++i) {
        const float t = static_cast<float>(i) / kSr;
        const float n = r.next();
        const float h = n - hp.lp(n, 1500.f);                    // passa-alta: estalo
        ph += 2.f * static_cast<float>(kPi) * (60.f + 90.f * expdec(t, 0.03f)) / kSr;
        const float body = std::sin(ph) * expdec(t, 0.07f);
        const float rev = tail.lp(r.next(), 900.f) * expdec(t, 0.22f) * 0.35f;
        const float v = h * expdec(t, 0.035f) * 1.2f + body * 0.9f + rev;
        o[i] = std::tanh(2.f * v) ; prev = v;
    }
    (void)prev;
    norm(o); return o;
}

std::vector<float> s_whoosh() {
    auto o = make(0.9f);
    Rng r(3); Svf f;
    for (std::size_t i = 0; i < o.size(); ++i) {
        const float t = static_cast<float>(i) / kSr / 0.9f;       // 0..1
        const float env = std::sin(static_cast<float>(kPi) * t);
        const float fc = 350.f + 2800.f * std::sin(static_cast<float>(kPi) * t);
        float lo, bp, hp;
        f.run(r.next(), fc, 0.35f, lo, bp, hp);
        o[i] = bp * env * env * 1.5f;
    }
    norm(o); return o;
}

std::vector<float> s_laser() {
    auto o = make(0.45f);
    float ph = 0;
    for (std::size_t i = 0; i < o.size(); ++i) {
        const float t = static_cast<float>(i) / kSr;
        const float fr = 220.f + 2400.f * std::exp(-t / 0.07f);
        ph += 2.f * static_cast<float>(kPi) * fr / kSr;
        const float v = std::sin(ph) + 0.35f * std::sin(2.f * ph) + 0.15f * std::sin(3.f * ph);
        o[i] = v * expdec(t, 0.16f) * std::min(1.f, t / 0.002f);
    }
    norm(o); return o;
}

std::vector<float> s_boom() {
    auto o = make(1.3f);
    float ph = 0;
    Rng r(5); OnePole lpf;
    for (std::size_t i = 0; i < o.size(); ++i) {
        const float t = static_cast<float>(i) / kSr;
        const float fr = 36.f + 70.f * std::exp(-t / 0.09f);
        ph += 2.f * static_cast<float>(kPi) * fr / kSr;
        const float v = std::sin(ph) * expdec(t, 0.38f) + 0.25f * lpf.lp(r.next(), 400.f) * expdec(t, 0.05f);
        o[i] = std::tanh(2.4f * v) * std::min(1.f, t / 0.003f);
    }
    norm(o); return o;
}

std::vector<float> s_glass() {
    auto o = make(1.0f);
    Rng r(6); OnePole hp;
    std::vector<float> ticks;
    for (int i = 0; i < 70; ++i) ticks.push_back((0.002f + 0.5f * std::pow((r.next() + 1.f) * 0.5f, 2.f)));
    for (std::size_t i = 0; i < o.size(); ++i) {
        const float t = static_cast<float>(i) / kSr;
        const float n = r.next();
        float v = (n - hp.lp(n, 3500.f)) * expdec(t, 0.05f) * 0.9f;   // impacto
        for (float tk : ticks) {
            const float d = t - tk;
            if (d >= 0 && d < 0.04f) v += std::sin(2.f * static_cast<float>(kPi) * (4200.f + 3000.f * std::fmod(tk * 97.f, 1.f)) * d) * expdec(d, 0.006f) * 0.35f;
        }
        o[i] = v;
    }
    norm(o); return o;
}

std::vector<float> s_airhorn() {
    auto o = make(1.1f);
    const float base[3] = {440.f, 554.f, 659.f};
    float ph[3] = {0, 0, 0};
    OnePole lpf;
    for (std::size_t i = 0; i < o.size(); ++i) {
        const float t = static_cast<float>(i) / kSr;
        const float vib = 1.f + 0.006f * std::sin(2.f * static_cast<float>(kPi) * 6.f * t);
        float v = 0;
        for (int k = 0; k < 3; ++k) {
            ph[k] += base[k] * vib / kSr;
            ph[k] -= std::floor(ph[k]);
            v += (2.f * ph[k] - 1.f) + 0.5f * ((ph[k] < 0.5f) ? 1.f : -1.f);   // serra + quadrada
        }
        const float env = std::min(1.f, t / 0.02f) * (t > 0.95f ? std::max(0.f, (1.1f - t) / 0.15f) : 1.f);
        o[i] = lpf.lp(v * 0.2f, 3200.f) * env;
    }
    norm(o); return o;
}

std::vector<float> s_riser() {
    auto o = make(2.0f);
    Rng r(8); Svf f; float ph = 0;
    for (std::size_t i = 0; i < o.size(); ++i) {
        const float t = static_cast<float>(i) / kSr / 2.0f;
        const float fc = 300.f + 5700.f * t * t;
        float lo, bp, hp;
        f.run(r.next(), fc, 0.4f, lo, bp, hp);
        ph += 2.f * static_cast<float>(kPi) * (200.f + 1000.f * t * t) / kSr;
        o[i] = (bp * 1.3f + 0.25f * std::sin(ph)) * t * t;
    }
    norm(o); return o;
}

std::vector<float> s_scratch() {
    auto o = make(0.6f);
    Rng r(9); float ph = 0; OnePole lpf;
    for (std::size_t i = 0; i < o.size(); ++i) {
        const float t = static_cast<float>(i) / kSr;
        const float fr = 300.f + 700.f * std::sin(2.f * static_cast<float>(kPi) * (3.f + 6.f * t) * t);
        ph += std::fabs(fr) / kSr;
        ph -= std::floor(ph);
        const float v = (2.f * ph - 1.f) * 0.7f + r.next() * 0.3f;
        o[i] = lpf.lp(v, 4500.f) * std::min(1.f, t / 0.01f) * (t > 0.5f ? (0.6f - t) / 0.1f : 1.f);
    }
    norm(o); return o;
}

bool known_name(const std::string& n) {
    Sfx s;
    return sfx_from_name(n, s);
}

} // namespace

Pcm synth_raw(Sfx s);

const char* sfx_name(Sfx s) {
    static const char* names[] = {"explosion", "gunshot", "whoosh", "laser", "boom", "glass", "airhorn", "riser", "scratch"};
    const int i = static_cast<int>(s);
    return (i >= 0 && i < static_cast<int>(Sfx::Count)) ? names[i] : "";
}

bool sfx_from_name(const std::string& name, Sfx& out) {
    for (int i = 0; i < static_cast<int>(Sfx::Count); ++i) {
        if (name == sfx_name(static_cast<Sfx>(i))) {
            out = static_cast<Sfx>(i);
            return true;
        }
    }
    return false;
}

Pcm synth(Sfx s) {
    Pcm p = synth_raw(s);
    // fade de saída curto em todos: nenhum efeito termina com "clique" (o riser sobe até o fim)
    const std::size_t n = std::min<std::size_t>(p.size(), kAudioRate * 15 / 1000);
    for (std::size_t i = 0; i < n; ++i) {
        const float k = static_cast<float>(i) / static_cast<float>(n);
        p[p.size() - 1 - i] = static_cast<std::int16_t>(p[p.size() - 1 - i] * k);
    }
    return p;
}

Pcm synth_raw(Sfx s) {
    switch (s) {
        case Sfx::Explosion: return to_pcm(s_explosion());
        case Sfx::Gunshot: return to_pcm(s_gunshot());
        case Sfx::Whoosh: return to_pcm(s_whoosh());
        case Sfx::Laser: return to_pcm(s_laser());
        case Sfx::Boom: return to_pcm(s_boom());
        case Sfx::Glass: return to_pcm(s_glass());
        case Sfx::Airhorn: return to_pcm(s_airhorn());
        case Sfx::Riser: return to_pcm(s_riser());
        case Sfx::Scratch: return to_pcm(s_scratch());
        default: return {};
    }
}

Pcm to_mono_44k(const std::int16_t* in, std::size_t frames, int rate, int channels) {
    if (!in || frames == 0 || rate < 8000 || rate > 192000 || channels < 1 || channels > 8) return {};
    std::vector<float> mono(frames);
    for (std::size_t i = 0; i < frames; ++i) {
        float acc = 0;
        for (int c = 0; c < channels; ++c) acc += in[i * channels + c];
        mono[i] = acc / static_cast<float>(channels) / 32768.f;
    }
    std::vector<float> res;
    if (rate == kAudioRate) {
        res = std::move(mono);
    } else {
        const double ratio = static_cast<double>(rate) / kAudioRate;   // amostras de entrada por saída
        const std::size_t n = static_cast<std::size_t>(static_cast<double>(frames) / ratio);
        res.resize(n);
        for (std::size_t i = 0; i < n; ++i) {
            const double pos = static_cast<double>(i) * ratio;
            if (ratio > 1.0) {                                         // reduzindo: média da janela (anti-alias simples)
                const std::size_t a = static_cast<std::size_t>(pos);
                const std::size_t b = std::min(frames, static_cast<std::size_t>(pos + ratio) + 1);
                float acc = 0;
                for (std::size_t k = a; k < b; ++k) acc += mono[k];
                res[i] = acc / static_cast<float>(b - a);
            } else {                                                   // ampliando: interpolação linear
                const std::size_t a = static_cast<std::size_t>(pos);
                const std::size_t b = std::min(frames - 1, a + 1);
                const float fr = static_cast<float>(pos - static_cast<double>(a));
                res[i] = mono[a] * (1.f - fr) + mono[b] * fr;
            }
        }
    }
    return to_pcm(res);
}

void normalize_peak(Pcm& p, float target) {
    int peak = 0;
    for (auto v : p) peak = std::max(peak, std::abs(static_cast<int>(v)));
    if (peak < 64) return;  // silêncio/ruído de fundo: não amplifica
    const float k = target * 32767.f / static_cast<float>(peak);
    for (auto& v : p) v = static_cast<std::int16_t>(std::lrintf(std::max(-32767.f, std::min(32767.f, v * k))));
}

void fade_edges(Pcm& p, int ms) {
    const std::size_t n = std::min(p.size() / 2, static_cast<std::size_t>(std::max(0, ms)) * kAudioRate / 1000);
    for (std::size_t i = 0; i < n; ++i) {
        const float k = static_cast<float>(i) / static_cast<float>(n);
        p[i] = static_cast<std::int16_t>(p[i] * k);
        p[p.size() - 1 - i] = static_cast<std::int16_t>(p[p.size() - 1 - i] * k);
    }
}

namespace {
void put32(std::string& s, std::uint32_t v) { for (int i = 0; i < 4; ++i) s.push_back(static_cast<char>((v >> (8 * i)) & 0xff)); }
void put16(std::string& s, std::uint16_t v) { for (int i = 0; i < 2; ++i) s.push_back(static_cast<char>((v >> (8 * i)) & 0xff)); }
std::uint32_t get32(const unsigned char* p) { return p[0] | (p[1] << 8) | (p[2] << 16) | (static_cast<std::uint32_t>(p[3]) << 24); }
std::uint16_t get16(const unsigned char* p) { return static_cast<std::uint16_t>(p[0] | (p[1] << 8)); }

bool write_atomic(const std::string& path, const std::string& head, const void* data, std::size_t bytes) {
    const std::string tmp = path + ".part";
    FILE* f = std::fopen(tmp.c_str(), "wb");
    if (!f) return false;
    bool ok = std::fwrite(head.data(), 1, head.size(), f) == head.size();
    ok = ok && (bytes == 0 || std::fwrite(data, 1, bytes, f) == bytes);
    ok = ok && std::fflush(f) == 0 && ::fsync(::fileno(f)) == 0;
    ok = (std::fclose(f) == 0) && ok;
    if (!ok || std::rename(tmp.c_str(), path.c_str()) != 0) {
        std::remove(tmp.c_str());
        return false;
    }
    return true;
}
} // namespace

bool write_wav(const std::string& path, const Pcm& mono, int rate) {
    const std::uint32_t bytes = static_cast<std::uint32_t>(mono.size() * 2);
    std::string h = "RIFF";
    put32(h, 36 + bytes); h += "WAVEfmt ";
    put32(h, 16); put16(h, 1); put16(h, 1); put32(h, static_cast<std::uint32_t>(rate));
    put32(h, static_cast<std::uint32_t>(rate) * 2); put16(h, 2); put16(h, 16);
    h += "data"; put32(h, bytes);
    return write_atomic(path, h, mono.data(), bytes);   // little-endian nativo (ARM/x86)
}

bool read_wav(const std::string& path, std::vector<std::int16_t>& data, int& rate, int& channels) {
    std::ifstream in(path, std::ios::binary);
    if (!in) return false;
    std::string buf((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
    if (buf.size() < 44 || buf.size() > (96u << 20)) return false;
    const auto* b = reinterpret_cast<const unsigned char*>(buf.data());
    if (std::memcmp(b, "RIFF", 4) != 0 || std::memcmp(b + 8, "WAVE", 4) != 0) return false;
    std::size_t pos = 12;
    bool have_fmt = false;
    int fr = 0, fc = 0, bits = 0, tag = 0;
    while (pos + 8 <= buf.size()) {
        const std::uint32_t size = get32(b + pos + 4);
        const std::size_t body = pos + 8;
        if (std::memcmp(b + pos, "fmt ", 4) == 0) {
            if (size < 16 || body + size > buf.size()) return false;
            tag = get16(b + body); fc = get16(b + body + 2); fr = static_cast<int>(get32(b + body + 4)); bits = get16(b + body + 14);
            have_fmt = true;
        } else if (std::memcmp(b + pos, "data", 4) == 0) {
            if (!have_fmt || tag != 1 || bits != 16 || fc < 1 || fc > 8 || fr < 8000 || fr > 192000) return false;
            // tamanho do chunk maior que o arquivo (stream/truncado): usa o que existe
            const std::size_t avail = std::min<std::size_t>(size, buf.size() - body);
            const std::size_t frames = avail / (2u * static_cast<std::size_t>(fc));
            if (frames == 0) return false;
            data.resize(frames * static_cast<std::size_t>(fc));
            std::memcpy(data.data(), b + body, data.size() * 2);
            rate = fr; channels = fc;
            return true;
        }
        pos = body + size + (size & 1u);
    }
    return false;
}

bool import_wav(const std::string& src, const std::string& dst, int max_ms) {
    std::vector<std::int16_t> raw;
    int rate = 0, ch = 0;
    if (!read_wav(src, raw, rate, ch)) return false;
    const std::size_t frames = raw.size() / static_cast<std::size_t>(ch);
    // corta antes de converter: clipes muito longos não ocupam memória à toa
    const std::size_t cap = static_cast<std::size_t>(rate) * static_cast<std::size_t>(std::max(1, max_ms)) / 1000u;
    Pcm p = to_mono_44k(raw.data(), std::min(frames, cap), rate, ch);
    if (p.empty()) return false;
    normalize_peak(p, 0.9f);
    fade_edges(p, 8);
    return write_wav(dst, p);
}

// --------------------------------------------------------------------------- linha do tempo de áudio
bool AudioTimeline::valid_source(const std::string& s) {
    if (s.rfind("sfx:", 0) == 0) return known_name(s.substr(4));
    if (s.rfind("file:", 0) == 0) return Timeline::valid_name(s.substr(5));
    return false;
}

void AudioTimeline::sort() {
    std::stable_sort(ev_.begin(), ev_.end(), [](const AudioEvent& a, const AudioEvent& b) { return a.start_us < b.start_us; });
}

bool AudioTimeline::add(std::int64_t start_us, int gain_milli, const std::string& source) {
    if (!valid_source(source) || ev_.size() >= kMaxEvents || start_us < 0 || start_us > 3600ll * 1000000) return false;
    ev_.push_back({start_us, std::clamp(gain_milli, 0, kMaxGain), source});
    sort();
    return true;
}

bool AudioTimeline::remove(std::size_t i) {
    if (i >= ev_.size()) return false;
    ev_.erase(ev_.begin() + static_cast<std::ptrdiff_t>(i));
    return true;
}

bool AudioTimeline::set_gain(std::size_t i, int g) {
    if (i >= ev_.size()) return false;
    ev_[i].gain_milli = std::clamp(g, 0, kMaxGain);
    return true;
}

bool AudioTimeline::set_start(std::size_t i, std::int64_t us) {
    if (i >= ev_.size() || us < 0 || us > 3600ll * 1000000) return false;
    ev_[i].start_us = us;
    sort();
    return true;
}

std::string AudioTimeline::serialize() const {
    std::ostringstream ss;
    ss << "VMA1\n";
    for (const auto& e : ev_) ss << "event " << e.start_us << " " << e.gain_milli << " " << e.source << "\n";
    return ss.str();
}

bool AudioTimeline::parse(const std::string& text) {
    std::istringstream in(text);
    std::string line;
    if (!std::getline(in, line) || line != "VMA1") return false;
    std::vector<AudioEvent> out;
    while (std::getline(in, line)) {
        if (line.empty()) continue;
        std::istringstream ls(line);
        std::string key;
        AudioEvent e;
        if (!(ls >> key >> e.start_us >> e.gain_milli >> e.source) || key != "event" || !valid_source(e.source) ||
            e.start_us < 0 || e.gain_milli < 0 || e.gain_milli > kMaxGain || out.size() >= kMaxEvents)
            return false;
        out.push_back(std::move(e));
    }
    ev_ = std::move(out);
    sort();
    return true;
}

bool AudioTimeline::save_atomic(const std::string& path) const {
    const std::string body = serialize();
    return write_atomic(path, body, nullptr, 0);
}

bool AudioTimeline::load(const std::string& path) {
    std::ifstream in(path, std::ios::binary);
    if (!in) return false;
    std::string body((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
    return parse(body);
}

// --------------------------------------------------------------------------- motor
const Pcm* AudioEngine::sample(const std::string& source) {
    auto it = bank_.find(source);
    if (it != bank_.end()) return &it->second;
    if (missing_.count(source)) return nullptr;
    Pcm p;
    if (source.rfind("sfx:", 0) == 0) {
        Sfx s;
        if (sfx_from_name(source.substr(4), s)) p = synth(s);
    } else if (source.rfind("file:", 0) == 0 && Timeline::valid_name(source.substr(5))) {
        std::vector<std::int16_t> raw;
        int rate = 0, ch = 0;
        if (read_wav(dir_ + "/" + source.substr(5), raw, rate, ch))
            p = to_mono_44k(raw.data(), raw.size() / static_cast<std::size_t>(ch), rate, ch);
    }
    if (p.empty()) {
        missing_[source] = true;   // não tenta reler a cada bloco de mixagem
        return nullptr;
    }
    return &(bank_[source] = std::move(p));
}

std::int64_t AudioEngine::source_duration_us(const std::string& source) {
    const Pcm* p = sample(source);
    return p ? static_cast<std::int64_t>(p->size()) * 1000000 / kAudioRate : 0;
}

void AudioEngine::render(std::int64_t start_frame, std::size_t n, std::int16_t* out) {
    if (!out || n == 0) return;
    std::vector<float> acc(n, 0.f);
    const std::int64_t end_frame = start_frame + static_cast<std::int64_t>(n);
    for (std::size_t i = 0; i < tl_.size(); ++i) {
        const AudioEvent& e = *tl_.at(i);
        const std::int64_t ev_start = e.start_us * kAudioRate / 1000000;
        if (ev_start >= end_frame) break;                       // eventos ordenados por início
        const Pcm* p = sample(e.source);
        if (!p) continue;
        const std::int64_t ev_end = ev_start + static_cast<std::int64_t>(p->size());
        if (ev_end <= start_frame) continue;
        const std::int64_t a = std::max(start_frame, ev_start), z = std::min(end_frame, ev_end);
        const float g = static_cast<float>(e.gain_milli) / 1000.f / 32768.f;
        for (std::int64_t f = a; f < z; ++f)
            acc[static_cast<std::size_t>(f - start_frame)] += static_cast<float>((*p)[static_cast<std::size_t>(f - ev_start)]) * g;
    }
    for (std::size_t i = 0; i < n; ++i)   // limitador suave: nunca estoura, mantém sinais baixos intactos
        out[i] = static_cast<std::int16_t>(std::lrintf(std::tanh(acc[i]) * 32767.f * 0.98f));
}

} // namespace vm
