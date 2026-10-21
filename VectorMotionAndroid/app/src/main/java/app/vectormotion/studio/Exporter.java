package app.vectormotion.studio;

import android.content.ContentResolver;
import android.content.ContentValues;
import android.content.Context;
import android.graphics.Bitmap;
import android.media.Image;
import android.media.MediaCodec;
import android.media.MediaCodecInfo;
import android.media.MediaFormat;
import android.media.MediaMuxer;
import android.net.Uri;
import android.os.Environment;
import android.os.Handler;
import android.os.Looper;
import android.os.ParcelFileDescriptor;
import android.provider.MediaStore;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;

/**
 * Renderiza a linha do tempo em MP4 vertical H.264 30 fps (formato Shorts/TikTok) em Movies/VectorMotion.
 * Frames passam pelo núcleo C++ (efeitos CGI + conversão RGBA→YUV) e entram no codec por ByteBuffer,
 * sem OpenGL. Salva via MediaStore: não precisa de permissão de armazenamento no Android 10.
 */
final class Exporter {
    interface Listener {
        void onProgress(float fraction);
        void onDone(Uri uri);
        void onError(String message);
    }

    private static final int OUT_FPS = 30;
    private static final long TIMEOUT_US = 10_000;

    private static final class Cancelled extends RuntimeException {}

    private final Context ctx;
    private final Project project;
    private final int preset;
    private final float intensity;
    private final Handler main = new Handler(Looper.getMainLooper());
    private volatile boolean cancelled;

    Exporter(Context ctx, Project project, int preset, float intensity) {
        this.ctx = ctx.getApplicationContext();
        this.project = project;
        this.preset = preset;
        this.intensity = intensity;
    }

    void start(Listener l) {
        new Thread(() -> run(l), "export").start();
    }

    void cancel() {
        cancelled = true;
    }

    private void run(Listener l) {
        final long h = project.cloneTimeline();
        try {
            if (NativeCore.tlSize(h) == 0) {
                post(() -> l.onError("Não há frames para exportar."));
                return;
            }
            final int[][] sizes = {{1080, 1920}, {720, 1280}};
            String lastError = "Falha desconhecida";
            for (int[] s : sizes) {
                Uri uri = null;
                try {
                    uri = createEntry();
                    encode(h, uri, s[0], s[1], l);
                    final ContentValues done = new ContentValues();
                    done.put(MediaStore.Video.Media.IS_PENDING, 0);
                    ctx.getContentResolver().update(uri, done, null, null);
                    final Uri result = uri;
                    post(() -> l.onDone(result));
                    return;
                } catch (Cancelled c) {
                    delete(uri);
                    post(() -> l.onError("Exportação cancelada."));
                    return;
                } catch (Exception | OutOfMemoryError e) {
                    delete(uri);
                    lastError = e.getMessage() != null ? e.getMessage() : e.getClass().getSimpleName();
                }
            }
            final String msg = lastError;
            post(() -> l.onError("Não foi possível exportar: " + msg));
        } finally {
            NativeCore.tlFree(h);
        }
    }

    private void post(Runnable r) {
        main.post(r);
    }

    private Uri createEntry() throws IOException {
        final ContentValues v = new ContentValues();
        v.put(MediaStore.Video.Media.DISPLAY_NAME,
                "VectorMotion_" + new SimpleDateFormat("yyyyMMdd_HHmmss", Locale.US).format(new Date()) + ".mp4");
        v.put(MediaStore.Video.Media.MIME_TYPE, "video/mp4");
        v.put(MediaStore.Video.Media.RELATIVE_PATH, Environment.DIRECTORY_MOVIES + "/VectorMotion");
        v.put(MediaStore.Video.Media.IS_PENDING, 1);
        final Uri uri = ctx.getContentResolver().insert(MediaStore.Video.Media.EXTERNAL_CONTENT_URI, v);
        if (uri == null) throw new IOException("MediaStore recusou o arquivo");
        return uri;
    }

    private void delete(Uri uri) {
        if (uri == null) return;
        try {
            ctx.getContentResolver().delete(uri, null, null);
        } catch (RuntimeException ignored) {
            // já removido
        }
    }

    private void encode(long tl, Uri uri, int w, int h, Listener l) throws IOException {
        final ContentResolver cr = ctx.getContentResolver();
        final long totalUs = NativeCore.tlDurationUs(tl);
        final int totalOut = (int) Math.max(1, (totalUs * OUT_FPS + 999_999L) / 1_000_000L);

        MediaCodec codec = null;
        MediaMuxer muxer = null;
        Bitmap cur = null;
        boolean muxerStarted = false;
        try (ParcelFileDescriptor pfd = cr.openFileDescriptor(uri, "rw")) {
            if (pfd == null) throw new IOException("Sem acesso ao arquivo de saída");
            final MediaFormat f = MediaFormat.createVideoFormat(MediaFormat.MIMETYPE_VIDEO_AVC, w, h);
            f.setInteger(MediaFormat.KEY_COLOR_FORMAT, MediaCodecInfo.CodecCapabilities.COLOR_FormatYUV420Flexible);
            f.setInteger(MediaFormat.KEY_BIT_RATE, w >= 1080 ? 10_000_000 : 6_000_000);
            f.setInteger(MediaFormat.KEY_FRAME_RATE, OUT_FPS);
            f.setInteger(MediaFormat.KEY_I_FRAME_INTERVAL, 1);
            f.setInteger(MediaFormat.KEY_COLOR_STANDARD, MediaFormat.COLOR_STANDARD_BT709);
            f.setInteger(MediaFormat.KEY_COLOR_RANGE, MediaFormat.COLOR_RANGE_LIMITED);
            codec = MediaCodec.createEncoderByType(MediaFormat.MIMETYPE_VIDEO_AVC);
            codec.configure(f, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE);
            codec.start();
            muxer = new MediaMuxer(pfd.getFileDescriptor(), MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4);

            final MediaCodec.BufferInfo info = new MediaCodec.BufferInfo();
            int track = -1;
            int fed = 0;
            int lastPercent = -1;
            boolean inputDone = false;
            boolean outDone = false;
            String curName = null;

            while (!outDone) {
                if (cancelled) throw new Cancelled();

                if (!inputDone) {
                    final int ii = codec.dequeueInputBuffer(TIMEOUT_US);
                    if (ii >= 0) {
                        final long pts = (long) fed * 1_000_000L / OUT_FPS;
                        if (fed >= totalOut) {
                            codec.queueInputBuffer(ii, 0, 0, pts, MediaCodec.BUFFER_FLAG_END_OF_STREAM);
                            inputDone = true;
                        } else {
                            int ci = NativeCore.tlClipAtUs(tl, Math.min(pts, Math.max(0, totalUs - 1)));
                            if (ci < 0) ci = NativeCore.tlSize(tl) - 1;
                            final String name = NativeCore.tlFile(tl, ci);
                            if (!name.equals(curName)) {
                                Bitmap b = FrameRenderer.decode(project.file(name), 1);
                                if (b == null) throw new IOException("Frame corrompido: " + name);
                                if (preset != NativeCore.FX_NONE)
                                    NativeCore.fxApply(b, preset, intensity, name.hashCode());
                                if (b.getWidth() != w || b.getHeight() != h) {
                                    final Bitmap s = Bitmap.createScaledBitmap(b, w, h, true);
                                    if (s != b) b.recycle();
                                    b = s;
                                }
                                if (cur != null) cur.recycle();
                                cur = b;
                                curName = name;
                            }
                            final Image img = codec.getInputImage(ii);
                            if (img == null) throw new IOException("Codec sem entrada por imagem");
                            final Image.Plane[] p = img.getPlanes();
                            if (!NativeCore.bitmapToYuv420(cur,
                                    p[0].getBuffer(), p[0].getRowStride(), p[0].getPixelStride(),
                                    p[1].getBuffer(), p[1].getRowStride(), p[1].getPixelStride(),
                                    p[2].getBuffer(), p[2].getRowStride(), p[2].getPixelStride()))
                                throw new IOException("Conversão de cor falhou");
                            codec.queueInputBuffer(ii, 0, w * h * 3 / 2, pts, 0);
                            fed++;
                            final int percent = fed * 100 / totalOut;
                            if (percent != lastPercent) {
                                lastPercent = percent;
                                final float frac = fed / (float) totalOut;
                                post(() -> l.onProgress(frac));
                            }
                        }
                    }
                }

                while (true) {
                    final int oi = codec.dequeueOutputBuffer(info, inputDone ? TIMEOUT_US : 0);
                    if (oi == MediaCodec.INFO_TRY_AGAIN_LATER) break;
                    if (oi == MediaCodec.INFO_OUTPUT_FORMAT_CHANGED) {
                        if (muxerStarted) throw new IOException("Formato mudou durante a gravação");
                        track = muxer.addTrack(codec.getOutputFormat());
                        muxer.start();
                        muxerStarted = true;
                        continue;
                    }
                    if (oi < 0) continue;
                    final ByteBuffer ob = codec.getOutputBuffer(oi);
                    if ((info.flags & MediaCodec.BUFFER_FLAG_CODEC_CONFIG) != 0) info.size = 0;
                    if (info.size > 0 && muxerStarted && ob != null) {
                        ob.position(info.offset);
                        ob.limit(info.offset + info.size);
                        muxer.writeSampleData(track, ob, info);
                    }
                    codec.releaseOutputBuffer(oi, false);
                    if ((info.flags & MediaCodec.BUFFER_FLAG_END_OF_STREAM) != 0) {
                        outDone = true;
                        break;
                    }
                }
            }
            if (!muxerStarted) throw new IOException("Codec não produziu vídeo");
            muxer.stop();
        } finally {
            if (cur != null) cur.recycle();
            if (codec != null) {
                try {
                    codec.stop();
                } catch (RuntimeException ignored) {
                    // já parado
                }
                codec.release();
            }
            if (muxer != null) {
                try {
                    muxer.release();
                } catch (RuntimeException ignored) {
                    // não iniciado ou já liberado
                }
            }
        }
    }
}
