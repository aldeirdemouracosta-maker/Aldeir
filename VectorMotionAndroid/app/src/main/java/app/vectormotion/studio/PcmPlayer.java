package app.vectormotion.studio;

import android.media.AudioAttributes;
import android.media.AudioFormat;
import android.media.AudioTrack;

/** Toca um buffer PCM mono 44,1 kHz (prévia de efeitos e áudio da reprodução), uma instância por vez. */
final class PcmPlayer {
    private AudioTrack track;

    synchronized void playOnce(short[] pcm) {
        start(pcm, false);
    }

    synchronized void playLoop(short[] pcm) {
        start(pcm, true);
    }

    private void start(short[] pcm, boolean loop) {
        stop();
        if (pcm == null || pcm.length < 64) return;
        try {
            final AudioTrack t = new AudioTrack.Builder()
                    .setAudioAttributes(new AudioAttributes.Builder()
                            .setUsage(AudioAttributes.USAGE_MEDIA)
                            .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC).build())
                    .setAudioFormat(new AudioFormat.Builder()
                            .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                            .setSampleRate(NativeCore.AUDIO_RATE)
                            .setChannelMask(AudioFormat.CHANNEL_OUT_MONO).build())
                    .setBufferSizeInBytes(pcm.length * 2)
                    .setTransferMode(AudioTrack.MODE_STATIC)
                    .build();
            if (t.write(pcm, 0, pcm.length) != pcm.length) {
                t.release();
                return;
            }
            if (loop) t.setLoopPoints(0, pcm.length, -1);
            t.play();
            track = t;
        } catch (RuntimeException e) {
            track = null;   // sem áudio de saída: o app segue mudo
        }
    }

    synchronized void stop() {
        if (track == null) return;
        try {
            track.stop();
        } catch (IllegalStateException ignored) {
            // não estava tocando
        }
        track.release();
        track = null;
    }
}
