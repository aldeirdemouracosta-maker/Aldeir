package app.vectormotion.studio;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.RectF;
import android.view.MotionEvent;
import android.view.View;

/** Botão em paralelogramo com ícone (ou texto) e rótulo; brilho vermelho quando ativo. */
final class HudButton extends View {
    private final int icon;
    private String label;
    private String iconText;
    private boolean active;
    private boolean pressedNow;
    private final Paint fill = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint stroke = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint glyph = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint text = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Path path = new Path();
    private final RectF rect = new RectF();

    HudButton(Context c, int icon, String label) {
        super(c);
        this.icon = icon;
        this.label = label;
        stroke.setStyle(Paint.Style.STROKE);
        stroke.setStrokeWidth(Theme.dp(1.5f));
        glyph.setStyle(Paint.Style.FILL);
        text.setTypeface(Theme.bold());
        text.setTextAlign(Paint.Align.CENTER);
        text.setLetterSpacing(0.06f);
        setClickable(true);
        setFocusable(true);
        setContentDescription(label);
    }

    void setActive(boolean a) {
        if (active != a) {
            active = a;
            invalidate();
        }
    }

    void setLabel(String l) {
        label = l;
        setContentDescription(l);
        invalidate();
    }

    /** Em vez do ícone, mostra texto grande (ex.: "12"). */
    void setIconText(String t) {
        iconText = t;
        invalidate();
    }

    @Override
    public void setEnabled(boolean e) {
        super.setEnabled(e);
        setAlpha(e ? 1f : 0.35f);
    }

    @Override
    public boolean onTouchEvent(MotionEvent e) {
        switch (e.getActionMasked()) {
            case MotionEvent.ACTION_DOWN:
                pressedNow = true;
                invalidate();
                break;
            case MotionEvent.ACTION_UP:
            case MotionEvent.ACTION_CANCEL:
                pressedNow = false;
                invalidate();
                break;
            default:
                break;
        }
        return super.onTouchEvent(e);
    }

    @Override
    protected void onMeasure(int wSpec, int hSpec) {
        final int w = MeasureSpec.getMode(wSpec) == MeasureSpec.UNSPECIFIED ? Theme.dpi(64) : MeasureSpec.getSize(wSpec);
        final int h = MeasureSpec.getMode(hSpec) == MeasureSpec.UNSPECIFIED ? Theme.dpi(54) : MeasureSpec.getSize(hSpec);
        setMeasuredDimension(w, h);
    }

    @Override
    protected void onDraw(Canvas c) {
        final float w = getWidth(), h = getHeight(), pad = Theme.dp(2);
        rect.set(pad, pad, w - pad, h - pad);
        Theme.slant(rect, Theme.dp(8), path);

        fill.setColor(pressedNow ? Theme.RED_DARK : (active ? 0xFF2A0E12 : Theme.PANEL2));
        if (active) fill.setShadowLayer(Theme.dp(8), 0, 0, Theme.RED);
        else fill.clearShadowLayer();
        c.drawPath(path, fill);
        fill.clearShadowLayer();
        stroke.setColor(active ? Theme.RED : Theme.LINE);
        c.drawPath(path, stroke);

        final boolean hasLabel = label != null && !label.isEmpty();
        final float iconCy = hasLabel ? h * 0.40f : h * 0.5f;
        final int ink = active ? Theme.GOLD : Theme.TEXT;
        if (iconText != null) {
            text.setColor(ink);
            text.setTextSize(Theme.dp(18));
            c.drawText(iconText, w / 2f, iconCy + Theme.dp(6), text);
        } else {
            glyph.setColor(ink);
            Icons.draw(c, icon, w / 2f, iconCy, Math.min(w, h) * 0.38f, glyph);
        }
        if (hasLabel) {
            text.setColor(active ? Theme.RED : Theme.MUTED);
            text.setTextSize(Theme.dp(9.5f));
            c.drawText(label.toUpperCase(), w / 2f, h - Theme.dp(8), text);
        }
    }
}
