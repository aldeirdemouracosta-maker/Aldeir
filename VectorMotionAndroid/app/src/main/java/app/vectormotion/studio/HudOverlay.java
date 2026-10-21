package app.vectormotion.studio;

import android.animation.ValueAnimator;
import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.view.View;

/** Moldura de HUD sobre a câmera: cantos de mira, marcador "REC" e retículo central. Não intercepta toques. */
final class HudOverlay extends View {
    private final Paint p = new Paint(Paint.ANTI_ALIAS_FLAG);
    private ValueAnimator blink;
    private float blinkT;
    private String tag = "AO VIVO";
    private int tagColor = Theme.RED;

    HudOverlay(Context c) {
        super(c);
        setClickable(false);
        p.setStrokeCap(Paint.Cap.SQUARE);
        p.setTypeface(Theme.bold());
        p.setLetterSpacing(0.1f);
    }

    void setTag(String t, int color) {
        tag = t;
        tagColor = color;
        invalidate();
    }

    @Override
    protected void onAttachedToWindow() {
        super.onAttachedToWindow();
        blink = ValueAnimator.ofFloat(0f, 1f);
        blink.setDuration(1100);
        blink.setRepeatCount(ValueAnimator.INFINITE);
        blink.addUpdateListener(a -> {
            blinkT = (float) a.getAnimatedValue();
            invalidate();
        });
        blink.start();
    }

    @Override
    protected void onDetachedFromWindow() {
        if (blink != null) blink.cancel();
        super.onDetachedFromWindow();
    }

    @Override
    protected void onDraw(Canvas c) {
        final float w = getWidth(), h = getHeight(), m = Theme.dp(10), len = Theme.dp(28);
        p.setStyle(Paint.Style.STROKE);
        p.setStrokeWidth(Theme.dp(3));
        p.setColor(Theme.RED);
        corner(c, m, m, len, 1, 1);
        corner(c, w - m, m, len, -1, 1);
        corner(c, m, h - m, len, 1, -1);
        corner(c, w - m, h - m, len, -1, -1);

        p.setStrokeWidth(Theme.dp(1.2f));
        p.setColor(0x66F5C518);
        final float cx = w / 2f, cy = h / 2f, a = Theme.dp(10);
        c.drawLine(cx - a, cy, cx + a, cy, p);
        c.drawLine(cx, cy - a, cx, cy + a, p);

        p.setStyle(Paint.Style.FILL);
        p.setColor(tagColor);
        p.setAlpha(blinkT < 0.5f ? 255 : 90);
        c.drawCircle(m + Theme.dp(8), m + Theme.dp(26), Theme.dp(4), p);
        p.setAlpha(255);
        p.setColor(Theme.TEXT);
        p.setTextSize(Theme.dp(11));
        c.drawText(tag, m + Theme.dp(18), m + Theme.dp(30), p);
    }

    private void corner(Canvas c, float x, float y, float len, int dx, int dy) {
        c.drawLine(x, y, x + dx * len, y, p);
        c.drawLine(x, y, x, y + dy * len, p);
    }
}
