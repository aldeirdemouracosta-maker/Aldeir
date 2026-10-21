package app.vectormotion.studio;

import android.animation.ValueAnimator;
import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.LinearGradient;
import android.graphics.RadialGradient;
import android.graphics.RectF;
import android.graphics.Shader;
import android.graphics.drawable.Drawable;
import android.view.MotionEvent;
import android.view.View;
import android.view.animation.DecelerateInterpolator;

import java.util.Random;

/** Abertura cinematográfica: faíscas, varredura de luz e título que "bate" na tela. */
final class SplashView extends View {
    interface Done {
        void onDone();
    }

    private static final int SPARKS = 46;
    private final Paint p = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Path path = new Path();
    private final RectF rect = new RectF();
    private final float[] sx = new float[SPARKS], sy = new float[SPARKS], sv = new float[SPARKS], ss = new float[SPARKS];
    private ValueAnimator anim;
    private float t;
    private boolean finished;
    private Done done;
    private volatile Bitmap art;   // cena de herói rasterizada uma vez, em segundo plano

    SplashView(Context c) {
        super(c);
        final Random r = new Random(7);
        for (int i = 0; i < SPARKS; i++) {
            sx[i] = r.nextFloat();
            sy[i] = r.nextFloat();
            sv[i] = 0.15f + r.nextFloat() * 0.5f;
            ss[i] = 1f + r.nextFloat() * 2.5f;
        }
        p.setTypeface(Theme.display());
        p.setTextAlign(Paint.Align.CENTER);
    }

    @Override
    protected void onSizeChanged(int w, int h, int ow, int oh) {
        super.onSizeChanged(w, h, ow, oh);
        if (w <= 0 || h <= 0 || art != null) return;
        final Context ctx = getContext();
        new Thread(() -> {
            try {
                final Drawable d = ctx.getDrawable(R.drawable.hero_scene);
                if (d == null) return;
                final Bitmap b = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888);
                final Canvas c = new Canvas(b);
                final float k = Math.max(w / 540f, h / 960f);
                c.translate((w - 540 * k) / 2f, (h - 960 * k) / 2f);
                c.scale(k, k);
                d.setBounds(0, 0, 540, 960);
                d.draw(c);
                art = b;
                postInvalidate();
            } catch (RuntimeException | OutOfMemoryError e) {
                // sem arte: a abertura segue só com os efeitos
            }
        }, "hero-art").start();
    }

    void start(Done d) {
        done = d;
        anim = ValueAnimator.ofFloat(0f, 1f);
        anim.setDuration(2300);
        anim.setInterpolator(new DecelerateInterpolator(0.6f));
        anim.addUpdateListener(a -> {
            t = (float) a.getAnimatedValue();
            invalidate();
            if (t >= 1f) finish();
        });
        anim.start();
    }

    private void finish() {
        if (finished) return;
        finished = true;
        if (anim != null) anim.cancel();
        if (done != null) done.onDone();
    }

    @Override
    public boolean onTouchEvent(MotionEvent e) {
        if (e.getActionMasked() == MotionEvent.ACTION_UP && t > 0.35f) finish();
        return true;
    }

    @Override
    protected void onDetachedFromWindow() {
        if (anim != null) anim.cancel();
        super.onDetachedFromWindow();
    }

    @Override
    protected void onDraw(Canvas c) {
        final float w = getWidth(), h = getHeight(), cx = w / 2f, cy = h * 0.80f;
        c.drawColor(Theme.BG);
        final Bitmap a = art;
        if (a != null) {
            p.setAlpha((int) (255 * Math.min(1f, 0.25f + t * 3f)));
            c.drawBitmap(a, 0, 0, p);
            p.setAlpha(255);
            p.setShader(new LinearGradient(0, h * 0.62f, 0, h, 0x00000000, 0xF2000000, Shader.TileMode.CLAMP));
            c.drawRect(0, h * 0.62f, w, h, p);
            p.setShader(new LinearGradient(0, 0, 0, h * 0.18f, 0xAA000000, 0x00000000, Shader.TileMode.CLAMP));
            c.drawRect(0, 0, w, h * 0.18f, p);
            p.setShader(null);
        }

        // clarão central
        p.setStyle(Paint.Style.FILL);
        p.setShader(new RadialGradient(cx, cy, Math.max(w, h) * 0.7f,
                new int[]{0x55ED1D24, 0x1AED1D24, 0x00000000}, new float[]{0f, 0.5f, 1f}, Shader.TileMode.CLAMP));
        c.drawRect(0, 0, w, h, p);
        p.setShader(null);

        // faíscas subindo
        p.setColor(Theme.GOLD);
        for (int i = 0; i < SPARKS; i++) {
            final float y = (sy[i] - t * sv[i] + 1f) % 1f;
            p.setAlpha((int) (200 * (1f - Math.abs(0.5f - y) * 1.6f)));
            c.drawCircle(sx[i] * w, y * h, Theme.dp(ss[i]), p);
        }
        p.setAlpha(255);

        // faixas diagonais de luz
        final float sweep = (t * 1.6f) % 1f;
        p.setColor(0x12FFFFFF);
        for (int i = 0; i < 3; i++) {
            final float x = (sweep + i * 0.33f) % 1f * (w + h) - h * 0.5f;
            path.reset();
            path.moveTo(x, 0);
            path.lineTo(x + Theme.dp(40), 0);
            path.lineTo(x - h * 0.35f + Theme.dp(40), h);
            path.lineTo(x - h * 0.35f, h);
            path.close();
            c.drawPath(path, p);
        }

        // faixa vermelha com o título
        final float slam = clamp((t - 0.08f) / 0.35f);
        final float k = 1f + (1f - slam) * 2.4f;
        final float bw = w * 0.88f, bh = Theme.dp(72);
        rect.set(cx - bw / 2f, cy - bh / 2f, cx + bw / 2f, cy + bh / 2f);
        c.save();
        c.scale(k, k, cx, cy);
        p.setAlpha((int) (255 * slam));
        p.setColor(Theme.RED);
        p.setShadowLayer(Theme.dp(26) * slam, 0, 0, Theme.RED);
        c.drawPath(Theme.slant(rect, Theme.dp(26), path), p);
        p.clearShadowLayer();
        p.setColor(0xFFFFFFFF);
        p.setTextSize(Theme.dp(42));
        p.setLetterSpacing(0.06f);
        c.drawText("VECTOR MOTION", cx, cy + Theme.dp(14), p);
        p.setAlpha(255);
        c.restore();

        // subtítulo
        final float sub = clamp((t - 0.45f) / 0.3f);
        p.setTypeface(Theme.bold());
        p.setColor(Theme.GOLD);
        p.setAlpha((int) (255 * sub));
        p.setTextSize(Theme.dp(15));
        p.setLetterSpacing(0.35f);
        c.drawText("STOP-MOTION  •  CGI  •  SHORTS", cx, cy + bh / 2f + Theme.dp(38) - (1f - sub) * Theme.dp(10), p);
        p.setAlpha(255);
        p.setTypeface(Theme.display());

        // barra de carregamento
        final float lw = w * 0.5f;
        p.setColor(Theme.LINE);
        c.drawRect(cx - lw / 2f, h * 0.95f, cx + lw / 2f, h * 0.95f + Theme.dp(3), p);
        p.setColor(Theme.RED);
        c.drawRect(cx - lw / 2f, h * 0.95f, cx - lw / 2f + lw * t, h * 0.95f + Theme.dp(3), p);
    }

    private static float clamp(float v) {
        return v < 0f ? 0f : (v > 1f ? 1f : v);
    }
}
