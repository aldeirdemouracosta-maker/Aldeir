#include "vm/timeline.hpp"

#include <algorithm>
#include <cstdio>
#include <fstream>
#include <sstream>
#include <unistd.h>

namespace vm {

Timeline::Timeline(int fps) : fps_(12) { set_fps(fps); }

void Timeline::set_fps(int fps) { fps_ = std::clamp(fps, kMinFps, kMaxFps); }

// Nome de arquivo simples: impede "../", espaços e quebras de linha que
// corromperiam o formato de texto.
bool Timeline::valid_name(const std::string& name) {
    if (name.empty() || name.size() > 120 || name == "." || name == "..") return false;
    for (unsigned char c : name) {
        const bool ok = (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
                        (c >= '0' && c <= '9') || c == '_' || c == '-' || c == '.';
        if (!ok) return false;
    }
    return true;
}

bool Timeline::add(const std::string& file, int hold) {
    if (!valid_name(file) || clips_.size() >= kMaxClips) return false;
    clips_.push_back({file, std::clamp(hold, 1, kMaxHold)});
    return true;
}

bool Timeline::remove(std::size_t i) {
    if (i >= clips_.size()) return false;
    clips_.erase(clips_.begin() + static_cast<std::ptrdiff_t>(i));
    return true;
}

bool Timeline::duplicate(std::size_t i) {
    if (i >= clips_.size() || clips_.size() >= kMaxClips) return false;
    const Clip copy = clips_[i];
    clips_.insert(clips_.begin() + static_cast<std::ptrdiff_t>(i) + 1, copy);
    return true;
}

bool Timeline::move(std::size_t from, std::size_t to) {
    if (from >= clips_.size() || to >= clips_.size()) return false;
    if (from == to) return true;
    Clip c = clips_[from];
    clips_.erase(clips_.begin() + static_cast<std::ptrdiff_t>(from));
    clips_.insert(clips_.begin() + static_cast<std::ptrdiff_t>(to), c);
    return true;
}

bool Timeline::set_hold(std::size_t i, int hold) {
    if (i >= clips_.size()) return false;
    clips_[i].hold = std::clamp(hold, 1, kMaxHold);
    return true;
}

bool Timeline::references(const std::string& file) const {
    return std::any_of(clips_.begin(), clips_.end(),
                       [&](const Clip& c) { return c.file == file; });
}

std::int64_t Timeline::total_frames() const {
    std::int64_t n = 0;
    for (const auto& c : clips_) n += c.hold;
    return n;
}

std::int64_t Timeline::duration_us() const {
    return total_frames() * 1000000 / fps_;
}

int Timeline::clip_at_time_us(std::int64_t us) const {
    if (us < 0 || clips_.empty() || us >= duration_us()) return -1;
    const std::int64_t frame = us * fps_ / 1000000;
    std::int64_t acc = 0;
    for (std::size_t i = 0; i < clips_.size(); ++i) {
        acc += clips_[i].hold;
        if (frame < acc) return static_cast<int>(i);
    }
    return -1;
}

std::string Timeline::serialize() const {
    std::ostringstream ss;
    ss << "VMT1\nfps " << fps_ << "\n";
    for (const auto& c : clips_) ss << "clip " << c.hold << " " << c.file << "\n";
    return ss.str();
}

bool Timeline::parse(const std::string& text) {
    std::istringstream in(text);
    std::string line;
    if (!std::getline(in, line) || line != "VMT1") return false;
    int fps = 0;
    std::vector<Clip> clips;
    while (std::getline(in, line)) {
        if (line.empty()) continue;
        std::istringstream ls(line);
        std::string key;
        ls >> key;
        if (key == "fps") {
            if (!(ls >> fps)) return false;
        } else if (key == "clip") {
            Clip c;
            if (!(ls >> c.hold >> c.file) || !valid_name(c.file) || c.hold < 1 ||
                c.hold > kMaxHold || clips.size() >= kMaxClips)
                return false;
            clips.push_back(std::move(c));
        } else {
            return false;
        }
    }
    if (fps < kMinFps || fps > kMaxFps) return false;
    fps_ = fps;
    clips_ = std::move(clips);
    return true;
}

// tmp + fsync + rename: queda de energia ou app morto não deixa arquivo pela metade.
bool Timeline::save_atomic(const std::string& path) const {
    const std::string tmp = path + ".part";
    const std::string body = serialize();
    FILE* f = std::fopen(tmp.c_str(), "wb");
    if (!f) return false;
    bool ok = std::fwrite(body.data(), 1, body.size(), f) == body.size();
    ok = ok && std::fflush(f) == 0 && ::fsync(::fileno(f)) == 0;
    ok = (std::fclose(f) == 0) && ok;
    if (!ok || std::rename(tmp.c_str(), path.c_str()) != 0) {
        std::remove(tmp.c_str());
        return false;
    }
    return true;
}

bool Timeline::load(const std::string& path) {
    std::ifstream in(path, std::ios::binary);
    if (!in) return false;
    std::string body((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
    return parse(body);
}

} // namespace vm
