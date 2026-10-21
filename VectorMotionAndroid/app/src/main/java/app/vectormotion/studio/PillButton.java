package app.vectormotion.studio;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.RectF;
import android.view.MotionEvent;
import android.view.View;

/** Botão largo inclinado com texto; primário = vermelho cheio, secundário = contorno. */
final class PillButton extends View {
    private final String text;
    private final boolean primary;
    private boolean down;
    private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Path path = new Path();
    private final RectF rect = new RectF();

    PillButton(Context c, String text, boolean primary) {
        super(c);
        this.text = text;
        this.primary = primary;
        paint.setTypeface(Theme.display());
        paint.setTextAlign(Paint.Align.CENTER);
        paint.setLetterSpacing(0.08f);
        setClickable(true);
        setFocusable(true);
        setContentDescription(text);
    }

    @Override
    public boolean onTouchEvent(MotionEvent e) {
        final int a = e.getActionMasked();
        if (a == MotionEvent.ACTION_DOWN) {
            down = true;
            invalidate();
        } else if (a == MotionEvent.ACTION_UP || a == MotionEvent.ACTION_CANCEL) {
            down = false;
            invalidate();
        }
        return super.onTouchEvent(e);
    }

    @Override
    protected void onMeasure(int w, int h) {
        setMeasuredDimension(MeasureSpec.getSize(w), Theme.dpi(52));
    }

    @Override
    protected void onDraw(Canvas c) {
        rect.set(Theme.dp(3), Theme.dp(3), getWidth() - Theme.dp(3), getHeight() - Theme.dp(3));
        Theme.slant(rect, Theme.dp(12), path);
        paint.setStyle(Paint.Style.FILL);
        if (primary) {
            paint.setColor(down ? Theme.RED_DARK : Theme.RED);
            paint.setShadowLayer(Theme.dp(10), 0, 0, Theme.RED);
        } else {
            paint.setColor(down ? Theme.PANEL2 : Theme.PANEL);
        }
        c.drawPath(path, paint);
        paint.clearShadowLayer();
        if (!primary) {
            paint.setStyle(Paint.Style.STROKE);
            paint.setStrokeWidth(Theme.dp(1.5f));
            paint.setColor(Theme.LINE);
            c.drawPath(path, paint);
        }
        paint.setStyle(Paint.Style.FILL);
        paint.setColor(Theme.TEXT);
        paint.setTextSize(Theme.dp(17));
        c.drawText(text.toUpperCase(), getWidth() / 2f, getHeight() / 2f + Theme.dp(6), paint);
    }
}
