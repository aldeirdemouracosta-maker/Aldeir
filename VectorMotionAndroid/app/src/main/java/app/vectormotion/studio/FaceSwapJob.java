package app.vectormotion.studio;

import android.content.Context;
import android.graphics.Bitmap;
import android.net.Uri;
import android.os.Handler;
import android.os.Looper;

import java.io.IOException;

/**
 * Troca o rosto de um vídeo pelo rosto de uma foto. Tudo no aparelho: extrai quadros (no ritmo do projeto, máx. 8 s),
 * acha os pontos do rosto em cada quadro, suaviza o tremor, deforma o rosto da foto sobre eles (C++) e grava os quadros
 * no projeto. Os quadros trocados ficam marcados: a exportação põe o selo "CONTEÚDO ALTERADO" enquanto algum existir.
 */
final class FaceSwapJob {
    interface Listener {
        void onProgress(float fraction);
        void onDone(int swapped, int total);
        void onError(String message);
    }

    static final int MAX_MS = 8000;

    private final Context ctx;
    private final Project project;
    private final Uri video, photo;
    private final Handler main = new Handler(Looper.getMainLooper());
    private volatile boolean cancelled;

    FaceSwapJob(Context ctx, Project project, Uri video, Uri photo) {
        this.ctx = ctx.getApplicationContext();
        this.project = project;
        this.video = video;
        this.photo = photo;
    }

    void start(Listener l) {
        new Thread(() -> run(l), "faceswap").start();
    }

    void cancel() {
        cancelled = true;
    }

    private void run(Listener l) {
        long swapper = 0, smoother = 0;
        Bitmap face = null;
        try {
            face = PhotoLoader.load(ctx, photo, 1280);
            final float[] facePts;
            try (FaceLandmarks lm = FaceLandmarks.open(ctx, false)) {
                facePts = lm.detect(face, 0);
            }
            if (facePts == null) {
                fail(l, "Não encontrei um rosto na foto. Use uma foto frontal, nítida e bem iluminada.");
                return;
            }
            swapper = NativeCore.fsNew(face, facePts);
            if (swapper == 0) {
                fail(l, "O rosto da foto está pequeno ou cortado demais.");
                return;
            }
            smoother = NativeCore.smNew();
            final long sw = swapper, sm = smoother;
            final int fps = Math.min(24, project.fps());
            final int[] counts = {0, 0};   // trocados, entregues
            try (FaceLandmarks lm = FaceLandmarks.open(ctx, true)) {
                final int delivered = VideoFrames.forEach(ctx, video, fps, MAX_MS, 1080, 1920, (bm, i, total) -> {
                    try {
                        if (cancelled || project.count() >= Project.MAX_FRAMES) return false;
                        boolean swapped = false;
                        final long ts = (long) i * 1000L / fps;
                        final float[] pts = lm.detect(bm, ts);
                        if (pts != null) {
                            NativeCore.smFilter(sm, pts, ts / 1000.0);
                            swapped = NativeCore.fsApply(sw, bm, pts, 0.85f, 0.06f);
                        } else {
                            NativeCore.smReset(sm);   // rosto sumiu: recomeça a suavização
                        }
                        final String name = project.addFrame(bm);
                        if (swapped) {
                            project.markFaceSwap(name);
                            counts[0]++;
                        }
                        counts[1]++;
                        final float frac = (i + 1) / (float) total;
                        main.post(() -> l.onProgress(frac));
                        return true;
                    } finally {
                        bm.recycle();
                    }
                });
                if (delivered == 0) {
                    fail(l, "Não consegui extrair quadros do vídeo.");
                    return;
                }
            }
            final int swapped = counts[0], total = counts[1];
            main.post(() -> l.onDone(swapped, total));
        } catch (IOException e) {
            fail(l, e.getMessage() != null ? e.getMessage() : "Falha na troca de rosto.");
        } catch (RuntimeException | OutOfMemoryError e) {
            fail(l, "Falha na troca de rosto (memória ou formato).");
        } finally {
            if (swapper != 0) NativeCore.fsFree(swapper);
            if (smoother != 0) NativeCore.smFree(smoother);
            if (face != null) face.recycle();
        }
    }

    private void fail(Listener l, String msg) {
        main.post(() -> l.onError(msg));
    }
}
