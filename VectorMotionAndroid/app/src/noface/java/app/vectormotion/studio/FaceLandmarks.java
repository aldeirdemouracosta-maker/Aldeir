package app.vectormotion.studio;

import android.content.Context;
import android.graphics.Bitmap;

import java.io.Closeable;
import java.io.IOException;

/** Versão sem troca de rosto: não inclui a biblioteca de reconhecimento (APK menor). */
final class FaceLandmarks implements Closeable {
    private FaceLandmarks() {}

    static boolean supported() {
        return false;
    }

    static FaceLandmarks open(Context ctx, boolean video) throws IOException {
        throw new IOException("Esta versão do app não inclui troca de rosto.");
    }

    /** 956 floats (478 pontos x,y em pixels) ou null se não houver rosto. */
    float[] detect(Bitmap bmp, long timestampMs) {
        return null;
    }

    @Override
    public void close() {}
}
