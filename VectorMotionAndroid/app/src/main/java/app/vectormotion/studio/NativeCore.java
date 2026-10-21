package app.vectormotion.studio;

import android.graphics.Bitmap;

import java.nio.ByteBuffer;

/** Ponte JNI para o núcleo C++ (linha do tempo, efeitos CGI, conversão YUV). */
final class NativeCore {
    static {
        System.loadLibrary("vmcore");
    }

    static final int FX_NONE = 0, FX_HERO = 1, FX_ENERGY = 2, FX_COSMIC = 3, FX_NOIR = 4;

    private NativeCore() {}

    static native String version();

    static native long tlNew(int fps);
    static native long tlClone(long h);
    static native void tlFree(long h);
    static native int tlSize(long h);
    static native int tlFps(long h);
    static native void tlSetFps(long h, int fps);
    static native boolean tlAdd(long h, String file, int hold);
    static native boolean tlRemove(long h, int i);
    static native boolean tlDuplicate(long h, int i);
    static native boolean tlMove(long h, int from, int to);
    static native boolean tlSetHold(long h, int i, int hold);
    static native boolean tlReferences(long h, String file);
    static native String tlFile(long h, int i);
    static native int tlHold(long h, int i);
    static native long tlTotalFrames(long h);
    static native long tlDurationUs(long h);
    static native int tlClipAtUs(long h, long us);
    static native boolean tlSave(long h, String path);
    static native boolean tlLoad(long h, String path);

    /** Bitmap precisa ser mutável ARGB_8888. */
    static native boolean fxApply(Bitmap b, int preset, float intensity, int seed);
    static native boolean onionGhost(Bitmap b, int tintRgb, float strength);
    static native boolean bitmapToYuv420(Bitmap b,
            ByteBuffer y, int yRow, int yPix,
            ByteBuffer u, int uRow, int uPix,
            ByteBuffer v, int vRow, int vPix);
}
