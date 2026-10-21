#include <jni.h>
#include <android/bitmap.h>

#include <string>

#include "vm/audio.hpp"
#include "vm/face_swap.hpp"
#include "vm/pixel_ops.hpp"
#include "vm/timeline.hpp"

#define JNI(ret, name) extern "C" JNIEXPORT ret JNICALL Java_app_vectormotion_studio_NativeCore_##name

namespace {

vm::Timeline* tl(jlong h) { return reinterpret_cast<vm::Timeline*>(h); }
vm::AudioEngine* ae(jlong h) { return reinterpret_cast<vm::AudioEngine*>(h); }
vm::FaceSwapper* fsw(jlong h) { return reinterpret_cast<vm::FaceSwapper*>(h); }
vm::LandmarkSmoother* sms(jlong h) { return reinterpret_cast<vm::LandmarkSmoother*>(h); }

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

// ---------------------------------------------------------------- áudio
JNI(jlong, aeNew)(JNIEnv* env, jclass, jstring dir) { return reinterpret_cast<jlong>(new vm::AudioEngine(str(env, dir))); }
JNI(void, aeFree)(JNIEnv*, jclass, jlong h) { delete ae(h); }
JNI(jint, aeSize)(JNIEnv*, jclass, jlong h) { return h ? static_cast<jint>(ae(h)->timeline().size()) : 0; }
JNI(jlong, aeStartUs)(JNIEnv*, jclass, jlong h, jint i) {
    const vm::AudioEvent* e = (h && i >= 0) ? ae(h)->timeline().at(static_cast<size_t>(i)) : nullptr;
    return e ? e->start_us : 0;
}
JNI(jint, aeGain)(JNIEnv*, jclass, jlong h, jint i) {
    const vm::AudioEvent* e = (h && i >= 0) ? ae(h)->timeline().at(static_cast<size_t>(i)) : nullptr;
    return e ? e->gain_milli : 0;
}
JNI(jstring, aeSource)(JNIEnv* env, jclass, jlong h, jint i) {
    const vm::AudioEvent* e = (h && i >= 0) ? ae(h)->timeline().at(static_cast<size_t>(i)) : nullptr;
    return env->NewStringUTF(e ? e->source.c_str() : "");
}
JNI(jboolean, aeAdd)(JNIEnv* env, jclass, jlong h, jlong startUs, jint gain, jstring src) {
    return h && ae(h)->timeline().add(startUs, gain, str(env, src));
}
JNI(jboolean, aeRemove)(JNIEnv*, jclass, jlong h, jint i) { return h && i >= 0 && ae(h)->timeline().remove(static_cast<size_t>(i)); }
JNI(jboolean, aeSetGain)(JNIEnv*, jclass, jlong h, jint i, jint g) { return h && i >= 0 && ae(h)->timeline().set_gain(static_cast<size_t>(i), g); }
JNI(jboolean, aeSetStart)(JNIEnv*, jclass, jlong h, jint i, jlong us) { return h && i >= 0 && ae(h)->timeline().set_start(static_cast<size_t>(i), us); }
JNI(void, aeClear)(JNIEnv*, jclass, jlong h) { if (h) ae(h)->timeline().clear(); }
JNI(jstring, aeSerialize)(JNIEnv* env, jclass, jlong h) { return env->NewStringUTF(h ? ae(h)->timeline().serialize().c_str() : ""); }
JNI(jboolean, aeParse)(JNIEnv* env, jclass, jlong h, jstring t) { return h && ae(h)->timeline().parse(str(env, t)); }
JNI(jboolean, aeSave)(JNIEnv* env, jclass, jlong h, jstring p) { return h && ae(h)->timeline().save_atomic(str(env, p)); }
JNI(jboolean, aeLoad)(JNIEnv* env, jclass, jlong h, jstring p) { return h && ae(h)->timeline().load(str(env, p)); }
JNI(jlong, aeSourceDurationUs)(JNIEnv* env, jclass, jlong h, jstring src) { return h ? ae(h)->source_duration_us(str(env, src)) : 0; }

// Mistura n amostras (mono 44,1 kHz) a partir de startFrame para out[0..n).
JNI(jboolean, aeRender)(JNIEnv* env, jclass, jlong h, jlong startFrame, jshortArray out, jint n) {
    if (!h || !out || n <= 0 || env->GetArrayLength(out) < n) return JNI_FALSE;
    std::vector<std::int16_t> buf(static_cast<size_t>(n));
    ae(h)->render(startFrame, buf.size(), buf.data());
    env->SetShortArrayRegion(out, 0, n, buf.data());
    return JNI_TRUE;
}

JNI(jshortArray, sfxPreview)(JNIEnv* env, jclass, jstring name) {
    vm::Sfx s;
    if (!vm::sfx_from_name(str(env, name), s)) return nullptr;
    const vm::Pcm p = vm::synth(s);
    jshortArray arr = env->NewShortArray(static_cast<jsize>(p.size()));
    if (arr) env->SetShortArrayRegion(arr, 0, static_cast<jsize>(p.size()), p.data());
    return arr;
}

JNI(jboolean, wavImport)(JNIEnv* env, jclass, jstring src, jstring dst, jint maxMs) {
    return vm::import_wav(str(env, src), str(env, dst), maxMs) ? JNI_TRUE : JNI_FALSE;
}

// ---------------------------------------------------------------- troca de rosto
// pts: 478 pontos (x,y em pixels) intercalados = 956 floats.
JNI(jlong, fsNew)(JNIEnv* env, jclass, jobject bmp, jfloatArray pts) {
    Locked l(env, bmp);
    if (!l.px || !pts) return 0;
    const jsize n = env->GetArrayLength(pts);
    std::vector<float> xy(static_cast<size_t>(n));
    env->GetFloatArrayRegion(pts, 0, n, xy.data());
    auto* f = new vm::FaceSwapper();
    if (!f->init(l.data(), static_cast<int>(l.info.width), static_cast<int>(l.info.height), static_cast<int>(l.info.stride),
                 xy.data(), static_cast<int>(n))) {
        delete f;
        return 0;
    }
    return reinterpret_cast<jlong>(f);
}
JNI(void, fsFree)(JNIEnv*, jclass, jlong h) { delete fsw(h); }
JNI(jboolean, fsApply)(JNIEnv* env, jclass, jlong h, jobject bmp, jfloatArray pts, jfloat color, jfloat feather) {
    if (!h || !pts) return JNI_FALSE;
    Locked l(env, bmp);
    if (!l.px) return JNI_FALSE;
    const jsize n = env->GetArrayLength(pts);
    std::vector<float> xy(static_cast<size_t>(n));
    env->GetFloatArrayRegion(pts, 0, n, xy.data());
    vm::SwapParams p;
    p.color_strength = color;
    p.feather = feather;
    return fsw(h)->apply(l.data(), static_cast<int>(l.info.width), static_cast<int>(l.info.height),
                         static_cast<int>(l.info.stride), xy.data(), static_cast<int>(n), p) ? JNI_TRUE : JNI_FALSE;
}
JNI(jlong, smNew)(JNIEnv*, jclass) { return reinterpret_cast<jlong>(new vm::LandmarkSmoother()); }
JNI(void, smFree)(JNIEnv*, jclass, jlong h) { delete sms(h); }
JNI(void, smReset)(JNIEnv*, jclass, jlong h) { if (h) sms(h)->reset(); }
JNI(void, smFilter)(JNIEnv* env, jclass, jlong h, jfloatArray pts, jdouble tSec) {
    if (!h || !pts) return;
    const jsize n = env->GetArrayLength(pts);
    std::vector<float> xy(static_cast<size_t>(n));
    env->GetFloatArrayRegion(pts, 0, n, xy.data());
    sms(h)->filter(xy.data(), static_cast<int>(n), tSec);
    env->SetFloatArrayRegion(pts, 0, n, xy.data());
}
