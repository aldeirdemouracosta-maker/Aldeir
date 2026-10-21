package app.vectormotion.studio;

import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.util.LruCache;

import java.io.File;

/** Decodifica frames e aplica os efeitos CGI (núcleo C++), com cache em memória limitado por bytes. */
final class FrameRenderer {
    private final LruCache<String, Bitmap> previews = new LruCache<String, Bitmap>(48 * 1024 * 1024) {
        @Override
        protected int sizeOf(String k, Bitmap b) {
            return b.getByteCount();
        }
    };
    private final LruCache<String, Bitmap> thumbs = new LruCache<String, Bitmap>(8 * 1024 * 1024) {
        @Override
        protected int sizeOf(String k, Bitmap b) {
            return b.getByteCount();
        }
    };

    /** Decodifica como ARGB_8888 mutável; null se o arquivo estiver corrompido. */
    static Bitmap decode(File f, int sample) {
        final BitmapFactory.Options o = new BitmapFactory.Options();
        o.inSampleSize = Math.max(1, sample);
        o.inPreferredConfig = Bitmap.Config.ARGB_8888;
        o.inMutable = true;
        try {
            return BitmapFactory.decodeFile(f.getPath(), o);
        } catch (OutOfMemoryError e) {
            return null;
        }
    }

    /** Frame com efeitos para a tela; o resultado é compartilhado: não modificar nem reciclar. */
    Bitmap preview(File f, int preset, float intensity, int sample) {
        final int q = Math.round(intensity * 20f);
        final String key = f.getName() + '|' + preset + '|' + q + '|' + sample;
        Bitmap b = previews.get(key);
        if (b != null) return b;
        b = decode(f, sample);
        if (b == null) return null;
        if (preset != NativeCore.FX_NONE) NativeCore.fxApply(b, preset, q / 20f, f.getName().hashCode());
        previews.put(key, b);
        return b;
    }

    Bitmap thumb(File f) {
        final String key = f.getName();
        Bitmap b = thumbs.get(key);
        if (b != null) return b;
        b = decode(f, 8);
        if (b != null) thumbs.put(key, b);
        return b;
    }

    void clear() {
        previews.evictAll();
        thumbs.evictAll();
    }
}
