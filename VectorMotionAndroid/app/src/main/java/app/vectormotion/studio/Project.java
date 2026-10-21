package app.vectormotion.studio;

import android.content.Context;
import android.graphics.Bitmap;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;

/**
 * Projeto único em files/projects/default: frames JPEG + timeline.vmt (gravada atomicamente pelo núcleo C++).
 * Todas as operações são sincronizadas: a captura grava em outra thread enquanto a UI lê.
 */
final class Project {
    static final int MAX_FRAMES = 900;
    private static final int JPEG_QUALITY = 92;

    private final File dir;
    private final File frames;
    private final File audio;
    private final long tl;
    private final long ae;

    Project(Context ctx) {
        dir = new File(ctx.getFilesDir(), "projects/default");
        frames = new File(dir, "frames");
        //noinspection ResultOfMethodCallIgnored
        frames.mkdirs();
        audio = new File(dir, "audio");
        //noinspection ResultOfMethodCallIgnored
        audio.mkdirs();
        tl = NativeCore.tlNew(12);
        ae = NativeCore.aeNew(audio.getPath());
        NativeCore.aeLoad(ae, audioIndex().getPath());
        final boolean loaded = NativeCore.tlLoad(tl, timelineFile().getPath());
        if (!loaded) rebuildFromFrames();
        recover();
        recoverAudio();
    }

    private File audioIndex() {
        return new File(dir, "audio.vma");
    }

    /** Remove .part, eventos cujo arquivo sumiu e WAVs que nenhum evento usa. */
    private synchronized void recoverAudio() {
        boolean changed = false;
        for (int i = NativeCore.aeSize(ae) - 1; i >= 0; i--) {
            final String src = NativeCore.aeSource(ae, i);
            if (src.startsWith("file:") && !new File(audio, src.substring(5)).isFile()) {
                NativeCore.aeRemove(ae, i);
                changed = true;
            }
        }
        final File[] list = audio.listFiles();
        if (list != null) {
            for (File f : list) {
                final String n = f.getName();
                if (n.endsWith(".part") || (n.endsWith(".wav") && !audioUses("file:" + n))) //noinspection ResultOfMethodCallIgnored
                    f.delete();
            }
        }
        if (changed) saveAudio();
    }

    private boolean audioUses(String source) {
        for (int i = 0; i < NativeCore.aeSize(ae); i++) if (NativeCore.aeSource(ae, i).equals(source)) return true;
        return false;
    }

    private void saveAudio() {
        NativeCore.aeSave(ae, audioIndex().getPath());
    }

    File audioDir() {
        return audio;
    }

    synchronized int audioCount() {
        return NativeCore.aeSize(ae);
    }

    synchronized long audioStartUs(int i) {
        return NativeCore.aeStartUs(ae, i);
    }

    synchronized int audioGain(int i) {
        return NativeCore.aeGain(ae, i);
    }

    synchronized String audioSource(int i) {
        return NativeCore.aeSource(ae, i);
    }

    synchronized boolean audioAdd(long startUs, int gainMilli, String source) {
        final boolean ok = NativeCore.aeAdd(ae, Math.max(0, startUs), gainMilli, source);
        if (ok) saveAudio();
        return ok;
    }

    synchronized boolean audioSetGain(int i, int gainMilli) {
        final boolean ok = NativeCore.aeSetGain(ae, i, gainMilli);
        if (ok) saveAudio();
        return ok;
    }

    /** Remove o evento; o WAV só é apagado se nenhum outro evento o usa. */
    synchronized boolean audioRemove(int i) {
        final String src = NativeCore.aeSource(ae, i);
        if (!NativeCore.aeRemove(ae, i)) return false;
        if (src.startsWith("file:") && !audioUses(src)) //noinspection ResultOfMethodCallIgnored
            new File(audio, src.substring(5)).delete();
        saveAudio();
        return true;
    }

    /** Próximo nome livre: voz_001.wav / meme_001.wav. */
    synchronized String nextAudioName(String prefix) {
        int max = 0;
        final String[] names = audio.list();
        if (names != null) {
            for (String n : names) {
                if (n.startsWith(prefix + "_") && n.endsWith(".wav")) {
                    try {
                        max = Math.max(max, Integer.parseInt(n.substring(prefix.length() + 1, n.length() - 4)));
                    } catch (NumberFormatException ignored) {
                        // nome estranho
                    }
                }
            }
        }
        return String.format(java.util.Locale.US, "%s_%03d.wav", prefix, max + 1);
    }

    /** Instante (µs) em que o frame `index` começa na linha do tempo. */
    synchronized long frameStartUs(int index) {
        long frames = 0;
        for (int i = 0; i < index && i < NativeCore.tlSize(tl); i++) frames += NativeCore.tlHold(tl, i);
        return frames * 1_000_000L / NativeCore.tlFps(tl);
    }

    /** Motor de áudio independente (cópia dos eventos) para tocar/exportar em outra thread. Liberar com aeFree. */
    synchronized long newAudioSnapshot() {
        final long h = NativeCore.aeNew(audio.getPath());
        NativeCore.aeParse(h, NativeCore.aeSerialize(ae));
        return h;
    }

    private File timelineFile() {
        return new File(dir, "timeline.vmt");
    }

    /** Timeline ausente ou corrompida: reconstrói a partir dos JPEGs em ordem, em vez de descartar o trabalho. */
    private synchronized void rebuildFromFrames() {
        final String[] names = frames.list();
        if (names == null) return;
        java.util.Arrays.sort(names);
        boolean any = false;
        for (String n : names) {
            if (n.startsWith("frame_") && n.endsWith(".jpg") && NativeCore.tlAdd(tl, n, 1)) any = true;
        }
        if (any) save();
    }

    /** Limpa restos de queda: .part, clips cujo arquivo sumiu e JPEGs órfãos. */
    private synchronized void recover() {
        final File[] list = frames.listFiles();
        if (list != null) {
            for (File f : list) {
                if (f.getName().endsWith(".part")) //noinspection ResultOfMethodCallIgnored
                    f.delete();
            }
        }
        boolean changed = false;
        for (int i = NativeCore.tlSize(tl) - 1; i >= 0; i--) {
            if (!new File(frames, NativeCore.tlFile(tl, i)).isFile()) {
                NativeCore.tlRemove(tl, i);
                changed = true;
            }
        }
        final File[] after = frames.listFiles();
        if (after != null) {
            for (File f : after) {
                if (f.getName().endsWith(".jpg") && !NativeCore.tlReferences(tl, f.getName())) //noinspection ResultOfMethodCallIgnored
                    f.delete();
            }
        }
        if (changed) save();
    }

    synchronized void save() {
        NativeCore.tlSave(tl, timelineFile().getPath());
    }

    synchronized int count() {
        return NativeCore.tlSize(tl);
    }

    synchronized int fps() {
        return NativeCore.tlFps(tl);
    }

    synchronized void setFps(int fps) {
        NativeCore.tlSetFps(tl, fps);
        save();
    }

    synchronized String nameAt(int i) {
        return NativeCore.tlFile(tl, i);
    }

    synchronized int holdAt(int i) {
        return NativeCore.tlHold(tl, i);
    }

    synchronized long totalFrames() {
        return NativeCore.tlTotalFrames(tl);
    }

    synchronized long durationUs() {
        return NativeCore.tlDurationUs(tl);
    }

    File framesDir() {
        return frames;
    }

    File file(String name) {
        return new File(frames, name);
    }

    /** Cópia independente da linha do tempo (para reprodução/exportação em outra thread). Liberar com NativeCore.tlFree. */
    synchronized long cloneTimeline() {
        return NativeCore.tlClone(tl);
    }

    private int nextNumber() {
        int max = 0;
        final String[] names = frames.list();
        if (names != null) {
            for (String n : names) {
                if (n.startsWith("frame_") && n.endsWith(".jpg") && n.length() == 16) {
                    try {
                        max = Math.max(max, Integer.parseInt(n.substring(6, 12)));
                    } catch (NumberFormatException ignored) {
                        // nome estranho: ignora
                    }
                }
            }
        }
        return max + 1;
    }

    /** Grava o JPEG (tmp + rename) e anexa à linha do tempo. */
    synchronized String addFrame(Bitmap bm) throws IOException {
        if (NativeCore.tlSize(tl) >= MAX_FRAMES) throw new IOException("limite de frames");
        final String name = String.format(java.util.Locale.US, "frame_%06d.jpg", nextNumber());
        final File tmp = new File(frames, name + ".part");
        final File dst = new File(frames, name);
        try (FileOutputStream out = new FileOutputStream(tmp)) {
            if (!bm.compress(Bitmap.CompressFormat.JPEG, JPEG_QUALITY, out)) throw new IOException("falha ao comprimir");
            out.flush();
            out.getFD().sync();
        } catch (IOException e) {
            //noinspection ResultOfMethodCallIgnored
            tmp.delete();
            throw e;
        }
        if (!tmp.renameTo(dst)) {
            //noinspection ResultOfMethodCallIgnored
            tmp.delete();
            throw new IOException("falha ao publicar frame");
        }
        if (!NativeCore.tlAdd(tl, name, 1)) {
            //noinspection ResultOfMethodCallIgnored
            dst.delete();
            throw new IOException("linha do tempo recusou o frame");
        }
        save();
        return name;
    }

    /** Remove o clip; o arquivo só é apagado se nenhuma cópia (duplicata) ainda o usa. */
    synchronized boolean remove(int i) {
        final String name = NativeCore.tlFile(tl, i);
        if (!NativeCore.tlRemove(tl, i)) return false;
        if (!name.isEmpty() && !NativeCore.tlReferences(tl, name)) //noinspection ResultOfMethodCallIgnored
            new File(frames, name).delete();
        save();
        return true;
    }

    synchronized boolean duplicate(int i) {
        final boolean ok = NativeCore.tlDuplicate(tl, i);
        if (ok) save();
        return ok;
    }

    synchronized boolean move(int from, int to) {
        final boolean ok = NativeCore.tlMove(tl, from, to);
        if (ok) save();
        return ok;
    }

    synchronized boolean setHold(int i, int hold) {
        final boolean ok = NativeCore.tlSetHold(tl, i, hold);
        if (ok) save();
        return ok;
    }

    synchronized void clear() {
        for (int i = NativeCore.tlSize(tl) - 1; i >= 0; i--) NativeCore.tlRemove(tl, i);
        final File[] list = frames.listFiles();
        if (list != null) {
            for (File f : list) //noinspection ResultOfMethodCallIgnored
                f.delete();
        }
        save();
        NativeCore.aeClear(ae);
        final File[] wavs = audio.listFiles();
        if (wavs != null) {
            for (File f : wavs) //noinspection ResultOfMethodCallIgnored
                f.delete();
        }
        saveAudio();
    }
}
