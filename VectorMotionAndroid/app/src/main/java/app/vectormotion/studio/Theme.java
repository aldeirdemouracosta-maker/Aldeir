package app.vectormotion.studio;

import android.content.Context;
import android.graphics.Path;
import android.graphics.RectF;
import android.graphics.Typeface;
import android.util.TypedValue;
import android.view.Gravity;
import android.widget.TextView;

/** Paleta e utilidades do visual "blockbuster": preto profundo, vermelho herói, ouro e ciano de energia. */
final class Theme {
    static final int BG = 0xFF07080D;
    static final int PANEL = 0xFF0E1220;
    static final int PANEL2 = 0xFF151B2E;
    static final int RED = 0xFFED1D24;
    static final int RED_DARK = 0xFF8E0F14;
    static final int GOLD = 0xFFF5C518;
    static final int CYAN = 0xFF00E5FF;
    static final int TEXT = 0xFFF2F4F8;
    static final int MUTED = 0xFF8A93AD;
    static final int LINE = 0xFF2A3350;

    private static float density = 3f;

    private Theme() {}

    static void init(Context c) {
        density = c.getResources().getDisplayMetrics().density;
    }

    static float dp(float v) {
        return v * density;
    }

    static int dpi(float v) {
        return Math.round(v * density);
    }

    static Typeface display() {
        return Typeface.create("sans-serif-condensed", Typeface.BOLD_ITALIC);
    }

    static Typeface bold() {
        return Typeface.create("sans-serif-condensed", Typeface.BOLD);
    }

    /** Paralelogramo inclinado, assinatura visual da interface. */
    static Path slant(RectF r, float skew, Path out) {
        out.reset();
        out.moveTo(r.left + skew, r.top);
        out.lineTo(r.right, r.top);
        out.lineTo(r.right - skew, r.bottom);
        out.lineTo(r.left, r.bottom);
        out.close();
        return out;
    }

    static TextView label(Context c, String text, float sp, int color) {
        TextView t = new TextView(c);
        t.setText(text);
        t.setTextColor(color);
        t.setTextSize(TypedValue.COMPLEX_UNIT_SP, sp);
        t.setTypeface(bold());
        t.setLetterSpacing(0.08f);
        t.setAllCaps(true);
        t.setGravity(Gravity.CENTER);
        t.setIncludeFontPadding(false);
        return t;
    }
}
