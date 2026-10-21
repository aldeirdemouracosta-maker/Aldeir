// API C mínima sobre o núcleo de troca de rosto, para o protótipo em Python (ctypes). Mesmo código do app Android.
#include "vm/face_swap.hpp"

#if defined(_WIN32)
#define VM_API extern "C" __declspec(dllexport)
#else
#define VM_API extern "C" __attribute__((visibility("default")))
#endif

VM_API void* vm_fs_new(const unsigned char* rgba, int w, int h, const float* pts, int n) {
    auto* f = new vm::FaceSwapper();
    if (!f->init(rgba, w, h, w * 4, pts, n)) {
        delete f;
        return nullptr;
    }
    return f;
}
VM_API int vm_fs_apply(void* f, unsigned char* rgba, int w, int h, const float* pts, int n, float color, float feather) {
    if (!f) return 0;
    vm::SwapParams p;
    p.color_strength = color;
    p.feather = feather;
    return static_cast<vm::FaceSwapper*>(f)->apply(rgba, w, h, w * 4, pts, n, p) ? 1 : 0;
}
VM_API void vm_fs_free(void* f) { delete static_cast<vm::FaceSwapper*>(f); }
VM_API void* vm_sm_new() { return new vm::LandmarkSmoother(); }
VM_API void vm_sm_filter(void* s, float* pts, int n, double t) { if (s) static_cast<vm::LandmarkSmoother*>(s)->filter(pts, n, t); }
VM_API void vm_sm_reset(void* s) { if (s) static_cast<vm::LandmarkSmoother*>(s)->reset(); }
VM_API void vm_sm_free(void* s) { delete static_cast<vm::LandmarkSmoother*>(s); }
