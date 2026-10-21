package app.vectormotion.studio;

import android.content.Context;
import android.view.Gravity;
import android.widget.HorizontalScrollView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import java.util.Locale;

/** Painel "Som & Memes": botões de efeitos, importar meme, gravar voz e lista dos sons da linha do tempo. */
final class AudioPanel extends LinearLayout {
    interface Host {
        long cursorUs();
        String cursorLabel();
        void addSfx(String name);
        void importMeme();
        void toggleVoice();
        void changed();
    }

    private static final String[] SFX_LABEL = {"Explosão", "Tiro", "Whoosh", "Laser", "Boom", "Vidro", "Buzina", "Riser", "Scratch"};

    private final Project project;
    private final Host host;
    private final TextView cursor;
    private final LinearLayout list;
    private final HudButton voiceBtn;

    AudioPanel(Context c, Project project, Host host) {
        super(c);
        this.project = project;
        this.host = host;
        setOrientation(VERTICAL);

        cursor = Theme.label(c, "", 10, Theme.GOLD);
        addView(cursor, new LayoutParams(-1, -2));

        final HorizontalScrollView hs = new HorizontalScrollView(c);
        hs.setHorizontalScrollBarEnabled(false);
        final LinearLayout row = new LinearLayout(c);
        row.setOrientation(HORIZONTAL);
        row.setPadding(Theme.dpi(8), Theme.dpi(4), Theme.dpi(8), Theme.dpi(4));
        for (int i = 0; i < NativeCore.SFX.length; i++) {
            final String name = NativeCore.SFX[i];
            row.addView(chip(new HudButton(c, Icons.SOUND, SFX_LABEL[i]), v -> host.addSfx(name)));
        }
        row.addView(chip(new HudButton(c, Icons.PLUS, "Meme"), v -> host.importMeme()));
        voiceBtn = new HudButton(c, Icons.MIC, "Voz");
        row.addView(chip(voiceBtn, v -> host.toggleVoice()));
        hs.addView(row);
        addView(hs, new LayoutParams(-1, -2));

        final ScrollView sv = new ScrollView(c);
        sv.setVerticalScrollBarEnabled(false);
        list = new LinearLayout(c);
        list.setOrientation(VERTICAL);
        list.setPadding(Theme.dpi(10), 0, Theme.dpi(10), 0);
        sv.addView(list);
        addView(sv, new LayoutParams(-1, Theme.dpi(104)));
        refresh();
    }

    private HudButton chip(HudButton b, OnClickListener l) {
        b.setOnClickListener(l);
        b.setLayoutParams(new LayoutParams(Theme.dpi(62), Theme.dpi(52)));
        ((LayoutParams) b.getLayoutParams()).rightMargin = Theme.dpi(4);
        return b;
    }

    void setRecording(boolean on) {
        voiceBtn.setActive(on);
        voiceBtn.setLabel(on ? "Parar" : "Voz");
    }

    private static String pretty(String source) {
        if (source.startsWith("sfx:")) {
            for (int i = 0; i < NativeCore.SFX.length; i++) if (source.endsWith(NativeCore.SFX[i])) return SFX_LABEL[i];
            return source;
        }
        return source.startsWith("file:voz") ? "Voz" : "Meme " + source.replaceAll("\\D+", "");
    }

    /** Recria a lista a partir do projeto (fonte da verdade). */
    void refresh() {
        cursor.setText("Cursor: " + host.cursorLabel());
        list.removeAllViews();
        final Context c = getContext();
        final int n = project.audioCount();
        if (n == 0) {
            final TextView empty = Theme.label(c, "Toque num som para colocá-lo no cursor", 10, Theme.MUTED);
            empty.setGravity(Gravity.CENTER);
            list.addView(empty, new LayoutParams(-1, Theme.dpi(40)));
            return;
        }
        for (int i = 0; i < n; i++) {
            final int idx = i;
            final LinearLayout r = new LinearLayout(c);
            r.setOrientation(HORIZONTAL);
            r.setGravity(Gravity.CENTER_VERTICAL);
            final TextView name = Theme.label(c, String.format(Locale.US, "%s  •  %.1fs", pretty(project.audioSource(i)),
                    project.audioStartUs(i) / 1_000_000.0), 11, Theme.TEXT);
            name.setGravity(Gravity.START | Gravity.CENTER_VERTICAL);
            r.addView(name, new LayoutParams(0, -1, 1f));
            final TextView vol = Theme.label(c, (project.audioGain(i) / 10) + "%", 10, Theme.GOLD);
            r.addView(small(Icons.MINUS, v -> gain(idx, -250)), new LayoutParams(Theme.dpi(38), Theme.dpi(32)));
            r.addView(vol, new LayoutParams(Theme.dpi(42), -1));
            r.addView(small(Icons.PLUS, v -> gain(idx, 250)), new LayoutParams(Theme.dpi(38), Theme.dpi(32)));
            r.addView(small(Icons.TRASH, v -> {
                project.audioRemove(idx);
                refresh();
                host.changed();
            }), new LayoutParams(Theme.dpi(38), Theme.dpi(32)));
            list.addView(r, new LayoutParams(-1, Theme.dpi(34)));
        }
    }

    private void gain(int idx, int delta) {
        project.audioSetGain(idx, project.audioGain(idx) + delta);
        refresh();
        host.changed();
    }

    private HudButton small(int icon, OnClickListener l) {
        final HudButton b = new HudButton(getContext(), icon, "");
        b.setOnClickListener(l);
        return b;
    }
}
