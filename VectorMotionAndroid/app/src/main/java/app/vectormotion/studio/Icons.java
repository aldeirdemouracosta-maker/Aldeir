package app.vectormotion.studio;

import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.RectF;

/** Ícones desenhados em vetor (sem imagens, sem dependências). */
final class Icons {
    static final int ONION = 0, LOCK = 1, UNLOCK = 2, FX = 3, UNDO = 4, PLAY = 5, PAUSE = 6,
            TRASH = 7, COPY = 8, LEFT = 9, RIGHT = 10, EXPORT = 11, NEW = 12, CLOSE = 13,
            PLUS = 14, MINUS = 15, MIC = 16, SOUND = 17;

    private static final Path P = new Path();
    private static final RectF R = new RectF();

    private Icons() {}

    /** Desenha o ícone dentro de um quadrado de lado `s` centrado em (cx, cy). */
    static void draw(Canvas c, int icon, float cx, float cy, float s, Paint p) {
        final float h = s / 2f;
        final Paint.Style old = p.getStyle();
        final float oldW = p.getStrokeWidth();
        p.setStrokeCap(Paint.Cap.ROUND);
        p.setStrokeJoin(Paint.Join.ROUND);
        p.setStrokeWidth(Math.max(2f, s * 0.11f));
        switch (icon) {
            case ONION:
                p.setStyle(Paint.Style.STROKE);
                c.drawCircle(cx - h * 0.28f, cy, h * 0.62f, p);
                c.drawCircle(cx + h * 0.28f, cy, h * 0.62f, p);
                break;
            case LOCK:
            case UNLOCK:
                p.setStyle(Paint.Style.FILL);
                R.set(cx - h * 0.6f, cy - h * 0.1f, cx + h * 0.6f, cy + h * 0.8f);
                c.drawRoundRect(R, s * 0.08f, s * 0.08f, p);
                p.setStyle(Paint.Style.STROKE);
                R.set(cx - h * 0.38f, cy - h * 0.85f, cx + h * 0.38f, cy + h * 0.2f);
                if (icon == LOCK) c.drawArc(R, 180, 180, false, p);
                else c.drawArc(R, 180, 130, false, p);
                break;
            case FX:
                p.setStyle(Paint.Style.FILL);
                P.reset();
                P.moveTo(cx + h * 0.15f, cy - h);
                P.lineTo(cx - h * 0.55f, cy + h * 0.1f);
                P.lineTo(cx - h * 0.05f, cy + h * 0.1f);
                P.lineTo(cx - h * 0.2f, cy + h);
                P.lineTo(cx + h * 0.6f, cy - h * 0.25f);
                P.lineTo(cx + h * 0.08f, cy - h * 0.25f);
                P.close();
                c.drawPath(P, p);
                break;
            case UNDO:
                p.setStyle(Paint.Style.STROKE);
                R.set(cx - h * 0.7f, cy - h * 0.6f, cx + h * 0.7f, cy + h * 0.8f);
                c.drawArc(R, 200, 250, false, p);
                P.reset();
                P.moveTo(cx - h * 0.95f, cy - h * 0.55f);
                P.lineTo(cx - h * 0.62f, cy - h * 0.1f);
                P.lineTo(cx - h * 0.2f, cy - h * 0.62f);
                c.drawPath(P, p);
                break;
            case PLAY:
                p.setStyle(Paint.Style.FILL);
                P.reset();
                P.moveTo(cx - h * 0.5f, cy - h * 0.75f);
                P.lineTo(cx + h * 0.8f, cy);
                P.lineTo(cx - h * 0.5f, cy + h * 0.75f);
                P.close();
                c.drawPath(P, p);
                break;
            case PAUSE:
                p.setStyle(Paint.Style.FILL);
                R.set(cx - h * 0.6f, cy - h * 0.7f, cx - h * 0.15f, cy + h * 0.7f);
                c.drawRoundRect(R, 3, 3, p);
                R.set(cx + h * 0.15f, cy - h * 0.7f, cx + h * 0.6f, cy + h * 0.7f);
                c.drawRoundRect(R, 3, 3, p);
                break;
            case TRASH:
                p.setStyle(Paint.Style.STROKE);
                c.drawLine(cx - h * 0.8f, cy - h * 0.5f, cx + h * 0.8f, cy - h * 0.5f, p);
                R.set(cx - h * 0.55f, cy - h * 0.5f, cx + h * 0.55f, cy + h * 0.85f);
                c.drawRoundRect(R, 4, 4, p);
                c.drawLine(cx - h * 0.25f, cy - h * 0.85f, cx + h * 0.25f, cy - h * 0.85f, p);
                break;
            case COPY:
                p.setStyle(Paint.Style.STROKE);
                R.set(cx - h * 0.2f, cy - h * 0.2f, cx + h * 0.8f, cy + h * 0.85f);
                c.drawRoundRect(R, 4, 4, p);
                R.set(cx - h * 0.8f, cy - h * 0.85f, cx + h * 0.2f, cy + h * 0.2f);
                c.drawRoundRect(R, 4, 4, p);
                break;
            case LEFT:
            case RIGHT: {
                p.setStyle(Paint.Style.STROKE);
                final float d = icon == LEFT ? -1f : 1f;
                P.reset();
                P.moveTo(cx + d * h * 0.3f, cy - h * 0.7f);
                P.lineTo(cx - d * h * 0.45f, cy);
                P.lineTo(cx + d * h * 0.3f, cy + h * 0.7f);
                c.drawPath(P, p);
                break;
            }
            case EXPORT:
                p.setStyle(Paint.Style.STROKE);
                c.drawLine(cx, cy - h * 0.9f, cx, cy + h * 0.2f, p);
                P.reset();
                P.moveTo(cx - h * 0.5f, cy - h * 0.4f);
                P.lineTo(cx, cy - h * 0.95f);
                P.lineTo(cx + h * 0.5f, cy - h * 0.4f);
                c.drawPath(P, p);
                P.reset();
                P.moveTo(cx - h * 0.8f, cy + h * 0.1f);
                P.lineTo(cx - h * 0.8f, cy + h * 0.85f);
                P.lineTo(cx + h * 0.8f, cy + h * 0.85f);
                P.lineTo(cx + h * 0.8f, cy + h * 0.1f);
                c.drawPath(P, p);
                break;
            case NEW:
            case PLUS:
                p.setStyle(Paint.Style.STROKE);
                c.drawLine(cx - h * 0.7f, cy, cx + h * 0.7f, cy, p);
                c.drawLine(cx, cy - h * 0.7f, cx, cy + h * 0.7f, p);
                break;
            case MINUS:
                p.setStyle(Paint.Style.STROKE);
                c.drawLine(cx - h * 0.7f, cy, cx + h * 0.7f, cy, p);
                break;
            case CLOSE:
                p.setStyle(Paint.Style.STROKE);
                c.drawLine(cx - h * 0.6f, cy - h * 0.6f, cx + h * 0.6f, cy + h * 0.6f, p);
                c.drawLine(cx + h * 0.6f, cy - h * 0.6f, cx - h * 0.6f, cy + h * 0.6f, p);
                break;
            case MIC:
                p.setStyle(Paint.Style.FILL);
                R.set(cx - h * 0.28f, cy - h * 0.9f, cx + h * 0.28f, cy + h * 0.25f);
                c.drawRoundRect(R, h * 0.28f, h * 0.28f, p);
                p.setStyle(Paint.Style.STROKE);
                R.set(cx - h * 0.62f, cy - h * 0.5f, cx + h * 0.62f, cy + h * 0.55f);
                c.drawArc(R, 0, 180, false, p);
                c.drawLine(cx, cy + h * 0.55f, cx, cy + h * 0.9f, p);
                break;
            case SOUND:
                p.setStyle(Paint.Style.FILL);
                P.reset();
                P.moveTo(cx - h * 0.85f, cy - h * 0.3f);
                P.lineTo(cx - h * 0.4f, cy - h * 0.3f);
                P.lineTo(cx + h * 0.05f, cy - h * 0.75f);
                P.lineTo(cx + h * 0.05f, cy + h * 0.75f);
                P.lineTo(cx - h * 0.4f, cy + h * 0.3f);
                P.lineTo(cx - h * 0.85f, cy + h * 0.3f);
                P.close();
                c.drawPath(P, p);
                p.setStyle(Paint.Style.STROKE);
                R.set(cx - h * 0.35f, cy - h * 0.45f, cx + h * 0.45f, cy + h * 0.45f);
                c.drawArc(R, -50, 100, false, p);
                R.set(cx - h * 0.55f, cy - h * 0.8f, cx + h * 0.85f, cy + h * 0.8f);
                c.drawArc(R, -50, 100, false, p);
                break;
            default:
                break;
        }
        p.setStyle(old);
        p.setStrokeWidth(oldW);
    }
}
