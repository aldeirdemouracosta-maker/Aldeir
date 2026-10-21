#pragma once
#include <cstddef>
#include <cstdint>
#include <vector>

namespace vm {

struct Pt {
    float x, y;
};
struct Tri {
    int a, b, c;
};

// Pontos do MediaPipe Face Landmarker (478 pontos, x/y em pixels, intercalados).
constexpr int kFaceLandmarks = 478;

// Índices (no vetor de 478) que formam o contorno do rosto, em ordem de percurso.
int face_oval_count();
const int* face_oval_indices();

// Triangulação de Delaunay (Bowyer-Watson). Vazia se houver menos de 3 pontos ou pontos degenerados.
std::vector<Tri> delaunay(const std::vector<Pt>& pts);

// Filtro One-Euro por coordenada: tira o tremor dos pontos sem atrasar movimentos rápidos.
class LandmarkSmoother {
public:
    explicit LandmarkSmoother(float min_cutoff = 1.5f, float beta = 0.01f) : min_cutoff_(min_cutoff), beta_(beta) {}
    void reset() { have_ = false; }
    // `xy` tem `count` valores (x,y intercalados); filtrado no lugar. t_sec = instante do quadro.
    void filter(float* xy, int count, double t_sec);

private:
    float min_cutoff_, beta_;
    bool have_ = false;
    double last_t_ = 0;
    std::vector<float> x_, dx_;
};

struct SwapParams {
    float color_strength = 0.85f;  // 0 = sem correção de cor, 1 = estatística igual à do vídeo
    float feather = 0.06f;         // suavização da borda, fração da largura do rosto
};

// Troca de rosto por malha: deforma o rosto da foto sobre os pontos do rosto do quadro,
// corrige a cor e mistura com borda suave. Tudo em CPU, sem rede.
class FaceSwapper {
public:
    // Fonte: foto RGBA + 478 pontos. false se foto/pontos forem inválidos.
    bool init(const std::uint8_t* rgba, int w, int h, int stride, const float* xy, int count);
    bool ready() const { return !tris_.empty(); }
    // Aplica no quadro (RGBA, alfa preservado). false se os pontos do quadro forem inválidos.
    bool apply(std::uint8_t* rgba, int w, int h, int stride, const float* xy, int count, const SwapParams& p = {}) const;

private:
    std::vector<std::uint8_t> src_;
    int sw_ = 0, sh_ = 0;
    std::vector<Pt> sp_;        // pontos do subconjunto, na foto
    std::vector<Tri> tris_;     // triângulos sobre sp_
};

} // namespace vm
