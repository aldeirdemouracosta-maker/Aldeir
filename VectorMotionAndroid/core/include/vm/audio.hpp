#pragma once
#include <cstddef>
#include <cstdint>
#include <map>
#include <string>
#include <vector>

namespace vm {

constexpr int kAudioRate = 44100;
constexpr int kMaxClipMs = 8000;  // memes curtos
using Pcm = std::vector<std::int16_t>;  // mono, kAudioRate

enum class Sfx : int { Explosion = 0, Gunshot, Whoosh, Laser, Boom, Glass, Airhorn, Riser, Scratch, Count };

const char* sfx_name(Sfx s);                       // "explosion", "gunshot"...
bool sfx_from_name(const std::string& name, Sfx& out);
Pcm synth(Sfx s);                                  // determinístico, normalizado

// Converte PCM intercalado de qualquer taxa/canais para mono 44,1 kHz.
Pcm to_mono_44k(const std::int16_t* interleaved, std::size_t frames, int rate, int channels);
void normalize_peak(Pcm& p, float target = 0.9f);
void fade_edges(Pcm& p, int ms);

// WAV PCM16. read_wav devolve false para cabeçalho inválido/truncado.
bool write_wav(const std::string& path, const Pcm& mono, int rate = kAudioRate);
bool read_wav(const std::string& path, std::vector<std::int16_t>& data, int& rate, int& channels);
// Importa um WAV qualquer: mono 44,1k, no máximo kMaxClipMs, normalizado e com fade. Grava em dst.
bool import_wav(const std::string& src, const std::string& dst, int max_ms = kMaxClipMs);

struct AudioEvent {
    std::int64_t start_us = 0;
    int gain_milli = 1000;     // 0..kMaxGain
    std::string source;        // "sfx:<nome>" ou "file:<arquivo.wav>"
};

class AudioTimeline {
public:
    static constexpr int kMaxGain = 3000;
    static constexpr std::size_t kMaxEvents = 400;

    std::size_t size() const { return ev_.size(); }
    const AudioEvent* at(std::size_t i) const { return i < ev_.size() ? &ev_[i] : nullptr; }
    bool add(std::int64_t start_us, int gain_milli, const std::string& source);
    bool remove(std::size_t i);
    bool set_gain(std::size_t i, int gain_milli);
    bool set_start(std::size_t i, std::int64_t start_us);
    void clear() { ev_.clear(); }
    std::string serialize() const;
    bool parse(const std::string& text);
    bool save_atomic(const std::string& path) const;
    bool load(const std::string& path);
    static bool valid_source(const std::string& s);

private:
    std::vector<AudioEvent> ev_;  // ordenado por start_us
    void sort();
};

// Motor: linha do tempo + banco de amostras (SFX sintetizados e arquivos do projeto).
class AudioEngine {
public:
    explicit AudioEngine(std::string dir) : dir_(std::move(dir)) {}
    AudioTimeline& timeline() { return tl_; }
    const AudioTimeline& timeline() const { return tl_; }
    // Mistura [start_frame, start_frame+n) em `out` (int16). Amostras faltantes são ignoradas.
    void render(std::int64_t start_frame, std::size_t n, std::int16_t* out);
    // Duração em us do trecho de áudio de um evento (0 se não puder carregar).
    std::int64_t source_duration_us(const std::string& source);
    const Pcm* sample(const std::string& source);

private:
    std::string dir_;
    AudioTimeline tl_;
    std::map<std::string, Pcm> bank_;
    std::map<std::string, bool> missing_;
};

} // namespace vm
