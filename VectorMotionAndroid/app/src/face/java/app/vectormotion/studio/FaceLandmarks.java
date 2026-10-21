package app.vectormotion.studio;

import android.content.Context;
import android.graphics.Bitmap;

import com.google.mediapipe.framework.image.BitmapImageBuilder;
import com.google.mediapipe.framework.image.MPImage;
import com.google.mediapipe.tasks.components.containers.NormalizedLandmark;
import com.google.mediapipe.tasks.core.BaseOptions;
import com.google.mediapipe.tasks.vision.core.RunningMode;
import com.google.mediapipe.tasks.vision.facelandmarker.FaceLandmarker;
import com.google.mediapipe.tasks.vision.facelandmarker.FaceLandmarkerResult;

import java.io.Closeable;
import java.io.IOException;
import java.util.List;

/** Pontos do rosto (MediaPipe Face Landmarker) rodando no aparelho. Modelo em assets/face_landmarker.task. */
final class FaceLandmarks implements Closeable {
    private final FaceLandmarker landmarker;
    private final boolean video;

    private FaceLandmarks(FaceLandmarker l, boolean video) {
        this.landmarker = l;
        this.video = video;
    }

    static boolean supported() {
        return true;
    }

    /** video=true: modo vídeo (rastreia entre quadros, timestamps crescentes); false: foto avulsa. */
    static FaceLandmarks open(Context ctx, boolean video) throws IOException {
        try {
            final BaseOptions base = BaseOptions.builder().setModelAssetPath("face_landmarker.task").build();
            final FaceLandmarker.FaceLandmarkerOptions options = FaceLandmarker.FaceLandmarkerOptions.builder()
                    .setBaseOptions(base)
                    .setRunningMode(video ? RunningMode.VIDEO : RunningMode.IMAGE)
                    .setNumFaces(1)
                    .setMinFaceDetectionConfidence(0.5f)
                    .setMinFacePresenceConfidence(0.5f)
                    .setMinTrackingConfidence(0.5f)
                    .build();
            return new FaceLandmarks(FaceLandmarker.createFromOptions(ctx, options), video);
        } catch (RuntimeException e) {
            throw new IOException("Modelo de rosto indisponível (face_landmarker.task)", e);
        }
    }

    /** 956 floats (478 pontos x,y em pixels) ou null se não houver rosto. */
    float[] detect(Bitmap bmp, long timestampMs) {
        final MPImage img = new BitmapImageBuilder(bmp).build();
        final FaceLandmarkerResult r = video ? landmarker.detectForVideo(img, timestampMs) : landmarker.detect(img);
        if (r.faceLandmarks().isEmpty()) return null;
        final List<NormalizedLandmark> l = r.faceLandmarks().get(0);
        if (l.size() < 468) return null;
        final float[] xy = new float[956];
        for (int i = 0; i < 478; i++) {
            final NormalizedLandmark p = l.get(Math.min(i, l.size() - 1));   // sem íris: repete o último
            xy[2 * i] = p.x() * bmp.getWidth();
            xy[2 * i + 1] = p.y() * bmp.getHeight();
        }
        return xy;
    }

    @Override
    public void close() {
        landmarker.close();
    }
}
