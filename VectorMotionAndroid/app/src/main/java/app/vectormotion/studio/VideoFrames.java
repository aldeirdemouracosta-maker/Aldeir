package app.vectormotion.studio;

import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.Rect;
import android.media.MediaMetadataRetriever;
import android.net.Uri;

import java.io.IOException;

/** Extrai quadros de um vídeo (MediaMetadataRetriever), já recortados em 9:16, um por vez (não guarda a lista na memória). */
final class VideoFrames {
    interface Sink {
        /** @return false para parar. Quem recebe é dono do bitmap. */
        boolean onFrame(Bitmap frame, int index, int total) throws IOException;
    }

    private VideoFrames() {}

    /** Recorte central que cobre outW×outH, ARGB_8888 mutável (necessário para o núcleo C++). */
    static Bitmap coverCrop(Bitmap src, int outW, int outH) {
        final Bitmap out = Bitmap.createBitmap(outW, outH, Bitmap.Config.ARGB_8888);
        final float k = Math.max(outW / (float) src.getWidth(), outH / (float) src.getHeight());
        final int sw = Math.min(src.getWidth(), Math.round(outW / k)), sh = Math.min(src.getHeight(), Math.round(outH / k));
        final Rect from = new Rect((src.getWidth() - sw) / 2, (src.getHeight() - sh) / 2, (src.getWidth() + sw) / 2, (src.getHeight() + sh) / 2);
        new Canvas(out).drawBitmap(src, from, new Rect(0, 0, outW, outH), new Paint(Paint.FILTER_BITMAP_FLAG));
        return out;
    }

    /** @return quantos quadros foram entregues. */
    static int forEach(Context ctx, Uri uri, int fps, int maxMs, int outW, int outH, Sink sink) throws IOException {
        final MediaMetadataRetriever r = new MediaMetadataRetriever();
        try {
            r.setDataSource(ctx, uri);
            final String d = r.extractMetadata(MediaMetadataRetriever.METADATA_KEY_DURATION);
            long durMs;
            try {
                durMs = d == null ? 0 : Long.parseLong(d);
            } catch (NumberFormatException e) {
                durMs = 0;
            }
            if (durMs <= 0) throw new IOException("Não consegui ler esse vídeo.");
            final long useMs = Math.min(durMs, maxMs);
            final int total = (int) Math.max(1, useMs * fps / 1000);
            int delivered = 0;
            for (int i = 0; i < total; i++) {
                final Bitmap f = r.getFrameAtTime((long) i * 1_000_000L / fps, MediaMetadataRetriever.OPTION_CLOSEST);
                if (f == null) continue;   // quadro ilegível: pula
                final Bitmap out = coverCrop(f, outW, outH);
                f.recycle();
                delivered++;
                if (!sink.onFrame(out, i, total)) break;
            }
            return delivered;
        } catch (RuntimeException e) {
            throw new IOException("Não consegui ler esse vídeo.", e);
        } finally {
            r.release();
        }
    }
}
