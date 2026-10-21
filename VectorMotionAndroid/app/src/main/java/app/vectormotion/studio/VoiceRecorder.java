package app.vectormotion.studio;

import android.media.AudioFormat;
import android.media.AudioRecord;
import android.media.MediaRecorder;

import java.io.File;
import java.io.IOException;
import java.io.RandomAccessFile;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;

/** Grava narração do microfone em WAV mono 44,1 kHz (máx. 30 s). A permissão é checada antes, sem pedir de novo. */
final class VoiceRecorder {
    interface Done {
        void onFinished(File wav, String error);
    }

    static final int MAX_MS = 30_000;

    private volatile boolean running;
    private Thread thread;

    boolean isRecording() {
        return running;
    }

    @SuppressWarnings("MissingPermission")  // checada pela Activity antes de chamar
    boolean start(File out, android.os.Handler main, Done done) {
        if (running) return false;
        final int min = AudioRecord.getMinBufferSize(NativeCore.AUDIO_RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT);
        if (min <= 0) return false;
        final AudioRecord rec;
        try {
            rec = new AudioRecord(MediaRecorder.AudioSource.MIC, NativeCore.AUDIO_RATE,
                    AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT, min * 4);
        } catch (RuntimeException e) {
            return false;
        }
        if (rec.getState() != AudioRecord.STATE_INITIALIZED) {
            rec.release();
            return false;
        }
        running = true;
        thread = new Thread(() -> {
            String error = null;
            long bytes = 0;
            try (RandomAccessFile w = new RandomAccessFile(out, "rw")) {
                w.setLength(0);
                w.write(AudioDecoder.header(0, NativeCore.AUDIO_RATE, 1));
                final byte[] buf = new byte[min];
                final long limit = (long) NativeCore.AUDIO_RATE * 2 * MAX_MS / 1000;
                rec.startRecording();
                while (running && bytes < limit) {
                    final int n = rec.read(buf, 0, buf.length);
                    if (n < 0) {
                        error = "Falha ao ler o microfone";
                        break;
                    }
                    w.write(buf, 0, n);
                    bytes += n;
                }
                rec.stop();
                // corrige os tamanhos do cabeçalho
                final ByteBuffer sz = ByteBuffer.allocate(4).order(ByteOrder.LITTLE_ENDIAN);
                w.seek(4);
                w.write(sz.putInt(0, (int) (36 + bytes)).array());
                w.seek(40);
                w.write(sz.putInt(0, (int) bytes).array());
            } catch (IOException | RuntimeException e) {
                error = "Falha ao gravar a voz";
            } finally {
                rec.release();
                running = false;
            }
            final String err = (error == null && bytes < NativeCore.AUDIO_RATE / 5) ? "Gravação muito curta" : error;
            main.post(() -> done.onFinished(err == null ? out : null, err));
        }, "voice");
        thread.start();
        return true;
    }

    void stop() {
        running = false;
    }
}
