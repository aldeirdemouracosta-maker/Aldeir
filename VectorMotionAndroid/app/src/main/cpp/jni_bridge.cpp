#include <jni.h>
#include <android/bitmap.h>

#include <string>

#include "vm/pixel_ops.hpp"
#include "vm/timeline.hpp"

#define JNI(ret, name) extern "C" JNIEXPORT ret JNICALL Java_app_vectormotion_studio_NativeCore_##name

namespace {

vm::Timeline* tl(jlong h) { return reinterpret_cast<vm::Timeline*>(h); }

std::string str(JNIEnv* env, jstring s) {
    if (!s) return {};
    const char* c = env->GetStringUTFChars(s, nullptr);
    if (!c) return {};
    std::string out(c);
    env->ReleaseStringUTFChars(s, c);
    return out;
}

// Trava os pixels de um Bitmap RGBA_8888; devolve nullptr se não for suportado.
struct Locked {
    JNIEnv* env; jobject bmp; AndroidBitmapInfo info{}; void* px = nullptr;
    Locked(JNIEnv* e, jobject b) : env(e), bmp(b) {
        if (!b || AndroidBitmap_getInfo(e, b, &info) != ANDROID_BITMAP_RESULT_SUCCESS ||
            info.format != ANDROID_BITMAP_FORMAT_RGBA_8888 ||
            AndroidBitmap_lockPixels(e, b, &px) != ANDROID_BITMAP_RESULT_SUCCESS)
            px = nullptr;
    }
    ~Locked() { if (px) AndroidBitmap_unlockPixels(env, bmp); }
    std::uint8_t* data() const { return static_cast<std::uint8_t*>(px); }
};

vm::Plane plane(JNIEnv* env, jobject buf, jint row, jint pix) {
    auto* p = buf ? static_cast<std::uint8_t*>(env->GetDirectBufferAddress(buf)) : nullptr;
    const jlong cap = buf ? env->GetDirectBufferCapacity(buf) : 0;
    return {p, row, pix, cap > 0 ? static_cast<std::size_t>(cap) : 0};
}

} // namespace

JNI(jstring, version)(JNIEnv* env, jclass) { return env->NewStringUTF("vmcore 0.1"); }

JNI(jlong, tlNew)(JNIEnv*, jclass, jint fps) { return reinterpret_cast<jlong>(new vm::Timeline(fps)); }
JNI(jlong, tlClone)(JNIEnv*, jclass, jlong h) { return h ? reinterpret_cast<jlong>(new vm::Timeline(*tl(h))) : 0; }
JNI(void, tlFree)(JNIEnv*, jclass, jlong h) { delete tl(h); }
JNI(jint, tlSize)(JNIEnv*, jclass, jlong h) { return h ? static_cast<jint>(tl(h)->size()) : 0; }
JNI(jint, tlFps)(JNIEnv*, jclass, jlong h) { return h ? tl(h)->fps() : 12; }
JNI(void, tlSetFps)(JNIEnv*, jclass, jlong h, jint fps) { if (h) tl(h)->set_fps(fps); }
JNI(jboolean, tlAdd)(JNIEnv* env, jclass, jlong h, jstring f, jint hold) { return h && tl(h)->add(str(env, f), hold); }
JNI(jboolean, tlRemove)(JNIEnv*, jclass, jlong h, jint i) { return h && i >= 0 && tl(h)->remove(static_cast<size_t>(i)); }
JNI(jboolean, tlDuplicate)(JNIEnv*, jclass, jlong h, jint i) { return h && i >= 0 && tl(h)->duplicate(static_cast<size_t>(i)); }
JNI(jboolean, tlMove)(JNIEnv*, jclass, jlong h, jint a, jint b) {
    return h && a >= 0 && b >= 0 && tl(h)->move(static_cast<size_t>(a), static_cast<size_t>(b));
}
JNI(jboolean, tlSetHold)(JNIEnv*, jclass, jlong h, jint i, jint hold) {
    return h && i >= 0 && tl(h)->set_hold(static_cast<size_t>(i), hold);
}
JNI(jboolean, tlReferences)(JNIEnv* env, jclass, jlong h, jstring f) { return h && tl(h)->references(str(env, f)); }
JNI(jstring, tlFile)(JNIEnv* env, jclass, jlong h, jint i) {
    const vm::Clip* c = (h && i >= 0) ? tl(h)->at(static_cast<size_t>(i)) : nullptr;
    return env->NewStringUTF(c ? c->file.c_str() : "");
}
JNI(jint, tlHold)(JNIEnv*, jclass, jlong h, jint i) {
    const vm::Clip* c = (h && i >= 0) ? tl(h)->at(static_cast<size_t>(i)) : nullptr;
    return c ? c->hold : 0;
}
JNI(jlong, tlTotalFrames)(JNIEnv*, jclass, jlong h) { return h ? tl(h)->total_frames() : 0; }
JNI(jlong, tlDurationUs)(JNIEnv*, jclass, jlong h) { return h ? tl(h)->duration_us() : 0; }
JNI(jint, tlClipAtUs)(JNIEnv*, jclass, jlong h, jlong us) { return h ? tl(h)->clip_at_time_us(us) : -1; }
JNI(jboolean, tlSave)(JNIEnv* env, jclass, jlong h, jstring p) { return h && tl(h)->save_atomic(str(env, p)); }
JNI(jboolean, tlLoad)(JNIEnv* env, jclass, jlong h, jstring p) { return h && tl(h)->load(str(env, p)); }

JNI(jboolean, fxApply)(JNIEnv* env, jclass, jobject bmp, jint preset, jfloat intensity, jint seed) {
    Locked l(env, bmp);
    if (!l.px) return JNI_FALSE;
    vm::apply_fx(l.data(), static_cast<int>(l.info.width), static_cast<int>(l.info.height),
                 static_cast<int>(l.info.stride),
                 vm::params_for(static_cast<vm::FxPreset>(preset), intensity), static_cast<std::uint32_t>(seed));
    return JNI_TRUE;
}

JNI(jboolean, onionGhost)(JNIEnv* env, jclass, jobject bmp, jint tint, jfloat strength) {
    Locked l(env, bmp);
    if (!l.px) return JNI_FALSE;
    vm::onion_ghost(l.data(), static_cast<int>(l.info.width), static_cast<int>(l.info.height),
                    static_cast<int>(l.info.stride), static_cast<std::uint32_t>(tint) & 0xffffffu, strength);
    return JNI_TRUE;
}

JNI(jboolean, bitmapToYuv420)(JNIEnv* env, jclass, jobject bmp, jobject yb, jint yr, jint yp,
                              jobject ub, jint ur, jint up, jobject vb, jint vr, jint vp) {
    Locked l(env, bmp);
    if (!l.px) return JNI_FALSE;
    return vm::rgba_to_yuv420(l.data(), static_cast<int>(l.info.width), static_cast<int>(l.info.height),
                              static_cast<int>(l.info.stride), plane(env, yb, yr, yp),
                              plane(env, ub, ur, up), plane(env, vb, vr, vp)) ? JNI_TRUE : JNI_FALSE;
}
