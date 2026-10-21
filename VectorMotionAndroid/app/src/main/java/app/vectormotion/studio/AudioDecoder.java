package app.vectormotion.studio;

import android.content.Context;
import android.media.MediaCodec;
import android.media.MediaExtractor;
import android.media.MediaFormat;
import android.net.Uri;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.IOException;
import java.io.RandomAccessFile;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;

/** Decodifica o áudio de qualquer arquivo/vídeo (mp3, m4a, ogg, mp4...) para um WAV PCM16 temporário. */
final class AudioDecoder {
    private static final long TIMEOUT_US = 10_000;

    private AudioDecoder() {}

    /**
     * Para de decodificar após `maxMs` de áudio: memes são curtos e isso protege a memória
     * (um podcast de 2 h não é carregado inteiro).
     */
    static void decodeToWav(Context ctx, Uri uri, File out, int maxMs) throws IOException {
        final MediaExtractor ex = new MediaExtractor();
        MediaCodec codec = null;
        try {
            ex.setDataSource(ctx, uri, null);
            int track = -1;
            MediaFormat fmt = null;
            for (int i = 0; i < ex.getTrackCount(); i++) {
                final MediaFormat f = ex.getTrackFormat(i);
                final String mime = f.getString(MediaFormat.KEY_MIME);
                if (mime != null && mime.startsWith("audio/")) {
                    track = i;
                    fmt = f;
                    break;
                }
            }
            if (track < 0) throw new IOException("O arquivo não tem áudio");
            ex.selectTrack(track);
            codec = MediaCodec.createDecoderByType(fmt.getString(MediaFormat.KEY_MIME));
            codec.configure(fmt, null, null, 0);
            codec.start();

            int rate = fmt.getInteger(MediaFormat.KEY_SAMPLE_RATE);
            int channels = fmt.getInteger(MediaFormat.KEY_CHANNEL_COUNT);
            boolean floatPcm = false;
            final ByteArrayOutputStream pcm = new ByteArrayOutputStream();
            final MediaCodec.BufferInfo info = new MediaCodec.BufferInfo();
            boolean inputDone = false, outDone = false;
            long maxBytes = (long) rate * channels * 2 * maxMs / 1000;

            while (!outDone && pcm.size() < maxBytes) {
                if (!inputDone) {
                    final int ii = codec.dequeueInputBuffer(TIMEOUT_US);
                    if (ii >= 0) {
                        final ByteBuffer ib = codec.getInputBuffer(ii);
                        final int n = ib == null ? -1 : ex.readSampleData(ib, 0);
                        if (n < 0) {
                            codec.queueInputBuffer(ii, 0, 0, 0, MediaCodec.BUFFER_FLAG_END_OF_STREAM);
                            inputDone = true;
                        } else {
                            codec.queueInputBuffer(ii, 0, n, ex.getSampleTime(), 0);
                            ex.advance();
                        }
                    }
                }
                final int oi = codec.dequeueOutputBuffer(info, TIMEOUT_US);
                if (oi == MediaCodec.INFO_OUTPUT_FORMAT_CHANGED) {
                    final MediaFormat of = codec.getOutputFormat();
                    if (of.containsKey(MediaFormat.KEY_SAMPLE_RATE)) rate = of.getInteger(MediaFormat.KEY_SAMPLE_RATE);
                    if (of.containsKey(MediaFormat.KEY_CHANNEL_COUNT)) channels = of.getInteger(MediaFormat.KEY_CHANNEL_COUNT);
                    floatPcm = of.containsKey(MediaFormat.KEY_PCM_ENCODING)
                            && of.getInteger(MediaFormat.KEY_PCM_ENCODING) == android.media.AudioFormat.ENCODING_PCM_FLOAT;
                    maxBytes = (long) rate * channels * 2 * maxMs / 1000;
                } else if (oi >= 0) {
                    final ByteBuffer ob = codec.getOutputBuffer(oi);
                    if (ob != null && info.size > 0) {
                        ob.position(info.offset);
                        ob.limit(info.offset + info.size);
                        ob.order(ByteOrder.LITTLE_ENDIAN);
                        if (floatPcm) {
                            final java.nio.FloatBuffer fb = ob.asFloatBuffer();
                            final byte[] b = new byte[fb.remaining() * 2];
                            int k = 0;
                            while (fb.hasRemaining()) {
                                final int v = Math.round(Math.max(-1f, Math.min(1f, fb.get())) * 32767f);
                                b[k++] = (byte) v;
                                b[k++] = (byte) (v >> 8);
                            }
                            pcm.write(b, 0, b.length);
                        } else {
                            final byte[] b = new byte[info.size];
                            ob.get(b);
                            pcm.write(b, 0, b.length);
                        }
                    }
                    codec.releaseOutputBuffer(oi, false);
                    if ((info.flags & MediaCodec.BUFFER_FLAG_END_OF_STREAM) != 0) outDone = true;
                }
            }
            if (pcm.size() == 0 || channels < 1) throw new IOException("Não foi possível ler o áudio");
            writeWav(out, pcm.toByteArray(), rate, channels);
        } catch (RuntimeException e) {
            throw new IOException("Formato de áudio não suportado", e);
        } finally {
            if (codec != null) {
                try {
                    codec.stop();
                } catch (RuntimeException ignored) {
                    // já parado
                }
                codec.release();
            }
            ex.release();
        }
    }

    static void writeWav(File f, byte[] pcm, int rate, int channels) throws IOException {
        try (RandomAccessFile w = new RandomAccessFile(f, "rw")) {
            w.setLength(0);
            w.write(header(pcm.length, rate, channels));
            w.write(pcm);
        }
    }

    static byte[] header(int dataBytes, int rate, int channels) {
        final ByteBuffer b = ByteBuffer.allocate(44).order(ByteOrder.LITTLE_ENDIAN);
        b.put("RIFF".getBytes()).putInt(36 + dataBytes).put("WAVEfmt ".getBytes());
        b.putInt(16).putShort((short) 1).putShort((short) channels).putInt(rate);
        b.putInt(rate * channels * 2).putShort((short) (channels * 2)).putShort((short) 16);
        b.put("data".getBytes()).putInt(dataBytes);
        return b.array();
    }
}
