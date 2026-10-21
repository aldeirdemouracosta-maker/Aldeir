package app.vectormotion.studio;

import android.animation.ValueAnimator;
import android.content.Context;
import android.graphics.Canvas;
import android.graphics.DashPathEffect;
import android.graphics.Paint;
import android.graphics.RadialGradient;
import android.graphics.Shader;
import android.view.MotionEvent;
import android.view.View;
import android.view.animation.LinearInterpolator;

/** Botão de captura estilo "reator": anéis giratórios, núcleo pulsante e brilho vermelho. */
final class ReactorButton extends View {
    private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private ValueAnimator spin;
    private float angle;
    private float pulse;
    private boolean pressedNow;

    ReactorButton(Context c) {
        super(c);
        setClickable(true);
        setFocusable(true);
        setContentDescription("Capturar frame");
    }

    @Override
    protected void onAttachedToWindow() {
        super.onAttachedToWindow();
        spin = ValueAnimator.ofFloat(0f, 360f);
        spin.setDuration(6000);
        spin.setRepeatCount(ValueAnimator.INFINITE);
        spin.setInterpolator(new LinearInterpolator());
        spin.addUpdateListener(a -> {
            angle = (float) a.getAnimatedValue();
            pulse = 0.5f + 0.5f * (float) Math.sin(Math.toRadians(angle * 4));
            invalidate();
        });
        spin.start();
    }

    @Override
    protected void onDetachedFromWindow() {
        if (spin != null) spin.cancel();
        super.onDetachedFromWindow();
    }

    @Override
    public void setEnabled(boolean e) {
        super.setEnabled(e);
        setAlpha(e ? 1f : 0.4f);
    }

    @Override
    public boolean onTouchEvent(MotionEvent e) {
        final int a = e.getActionMasked();
        if (a == MotionEvent.ACTION_DOWN) {
            pressedNow = true;
            invalidate();
        } else if (a == MotionEvent.ACTION_UP || a == MotionEvent.ACTION_CANCEL) {
            pressedNow = false;
            invalidate();
        }
        return super.onTouchEvent(e);
    }

    @Override
    protected void onMeasure(int w, int h) {
        final int s = Theme.dpi(92);
        setMeasuredDimension(s, s);
    }

    @Override
    protected void onDraw(Canvas c) {
        final float cx = getWidth() / 2f, cy = getHeight() / 2f, r = Math.min(cx, cy);
        final float scale = pressedNow ? 0.92f : 1f;
        c.save();
        c.scale(scale, scale, cx, cy);

        // halo
        paint.setStyle(Paint.Style.FILL);
        paint.setShader(new RadialGradient(cx, cy, r, new int[]{0x00ED1D24, (0x30 + (int) (0x40 * pulse)) << 24 | 0xED1D24, 0x00ED1D24},
                new float[]{0.55f, 0.8f, 1f}, Shader.TileMode.CLAMP));
        c.drawCircle(cx, cy, r, paint);
        paint.setShader(null);

        // anel externo giratório tracejado
        paint.setStyle(Paint.Style.STROKE);
        paint.setStrokeWidth(Theme.dp(3));
        paint.setColor(Theme.RED);
        paint.setPathEffect(new DashPathEffect(new float[]{Theme.dp(14), Theme.dp(7)}, 0));
        c.save();
        c.rotate(angle, cx, cy);
        c.drawCircle(cx, cy, r * 0.82f, paint);
        c.restore();
        paint.setPathEffect(null);

        // anel dourado contra-giratório
        paint.setStrokeWidth(Theme.dp(1.5f));
        paint.setColor(Theme.GOLD);
        paint.setPathEffect(new DashPathEffect(new float[]{Theme.dp(4), Theme.dp(10)}, 0));
        c.save();
        c.rotate(-angle * 1.6f, cx, cy);
        c.drawCircle(cx, cy, r * 0.70f, paint);
        c.restore();
        paint.setPathEffect(null);

        // núcleo
        paint.setStyle(Paint.Style.FILL);
        final float core = r * (0.50f + 0.03f * pulse);
        paint.setShader(new RadialGradient(cx, cy, core, new int[]{0xFFFFFFFF, 0xFFFF6A5E, Theme.RED, Theme.RED_DARK},
                new float[]{0f, 0.35f, 0.75f, 1f}, Shader.TileMode.CLAMP));
        c.drawCircle(cx, cy, core, paint);
        paint.setShader(null);
        paint.setStyle(Paint.Style.STROKE);
        paint.setStrokeWidth(Theme.dp(2));
        paint.setColor(0xFFFFFFFF);
        c.drawCircle(cx, cy, core, paint);
        c.restore();
    }
}
