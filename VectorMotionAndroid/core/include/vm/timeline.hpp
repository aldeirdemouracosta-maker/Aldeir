#pragma once
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace vm {

struct Clip {
    std::string file;  // nome simples, sem diretório
    int hold = 1;      // quantos frames da timeline este clip ocupa
};

// Linha do tempo do stop-motion. Sem dependência de Android: testável no host.
class Timeline {
public:
    static constexpr int kMinFps = 1;
    static constexpr int kMaxFps = 60;
    static constexpr int kMaxHold = 240;
    static constexpr std::size_t kMaxClips = 2000;

    explicit Timeline(int fps = 12);

    int fps() const { return fps_; }
    void set_fps(int fps);

    std::size_t size() const { return clips_.size(); }
    const Clip* at(std::size_t i) const { return i < clips_.size() ? &clips_[i] : nullptr; }

    bool add(const std::string& file, int hold = 1);
    bool remove(std::size_t i);
    bool duplicate(std::size_t i);
    bool move(std::size_t from, std::size_t to);
    bool set_hold(std::size_t i, int hold);
    bool references(const std::string& file) const;

    std::int64_t total_frames() const;
    std::int64_t duration_us() const;
    // Índice do clip exibido no instante `us`; -1 se fora da duração.
    int clip_at_time_us(std::int64_t us) const;

    std::string serialize() const;
    bool parse(const std::string& text);
    bool save_atomic(const std::string& path) const;
    bool load(const std::string& path);

    static bool valid_name(const std::string& name);

private:
    int fps_;
    std::vector<Clip> clips_;
};

} // namespace vm
