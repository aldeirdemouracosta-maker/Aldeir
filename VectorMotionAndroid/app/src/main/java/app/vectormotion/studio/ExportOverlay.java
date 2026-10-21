package app.vectormotion.studio;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.RectF;
import android.net.Uri;
import android.view.Gravity;
import android.view.View;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.TextView;

/** Camada de exportação: progresso "CGI", e ao final botões para TikTok / outros apps. */
final class ExportOverlay extends FrameLayout {
    interface Actions {
        void onCancel();
        void onTikTok(Uri uri);
        void onShare(Uri uri);
        void onClose();
    }

    private static final class Bar extends View {
        float value;
        private final Paint p = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final Path path = new Path();
        private final RectF r = new RectF();

        Bar(Context c) {
            super(c);
        }

        @Override
        protected void onDraw(Canvas c) {
            r.set(0, 0, getWidth(), getHeight());
            p.setColor(Theme.LINE);
            c.drawPath(Theme.slant(r, Theme.dp(8), path), p);
            r.set(0, 0, Math.max(Theme.dp(10), getWidth() * value), getHeight());
            p.setColor(Theme.RED);
            p.setShadowLayer(Theme.dp(8), 0, 0, Theme.RED);
            c.drawPath(Theme.slant(r, Theme.dp(8), path), p);
            p.clearShadowLayer();
        }
    }

    private final TextView title;
    private final TextView detail;
    private final Bar bar;
    private final LinearLayout buttons;
    private final Actions actions;

    ExportOverlay(Context c, Actions actions) {
        super(c);
        this.actions = actions;
        setBackgroundColor(0xE6000000);
        setClickable(true);

        final LinearLayout card = new LinearLayout(c);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setPadding(Theme.dpi(24), Theme.dpi(24), Theme.dpi(24), Theme.dpi(24));
        card.setBackgroundColor(Theme.PANEL);
        final LayoutParams cp = new LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT, Gravity.CENTER);
        cp.leftMargin = cp.rightMargin = Theme.dpi(20);
        addView(card, cp);

        title = Theme.label(c, "Renderizando CGI", 20, Theme.TEXT);
        title.setTypeface(Theme.display());
        card.addView(title, new LinearLayout.LayoutParams(-1, -2));

        detail = Theme.label(c, "0%", 13, Theme.GOLD);
        final LinearLayout.LayoutParams dp = new LinearLayout.LayoutParams(-1, -2);
        dp.topMargin = Theme.dpi(8);
        card.addView(detail, dp);

        bar = new Bar(c);
        final LinearLayout.LayoutParams bp = new LinearLayout.LayoutParams(-1, Theme.dpi(14));
        bp.topMargin = Theme.dpi(16);
        card.addView(bar, bp);

        buttons = new LinearLayout(c);
        buttons.setOrientation(LinearLayout.VERTICAL);
        final LinearLayout.LayoutParams bl = new LinearLayout.LayoutParams(-1, -2);
        bl.topMargin = Theme.dpi(18);
        card.addView(buttons, bl);
        showButtons(cancelOnly());
    }

    private View[] cancelOnly() {
        final PillButton cancel = new PillButton(getContext(), "Cancelar", false);
        cancel.setOnClickListener(v -> actions.onCancel());
        return new View[]{cancel};
    }

    private void showButtons(View... views) {
        buttons.removeAllViews();
        for (View v : views) {
            final LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(-1, -2);
            lp.topMargin = Theme.dpi(8);
            buttons.addView(v, lp);
        }
    }

    void setProgress(float f) {
        bar.value = Math.max(0f, Math.min(1f, f));
        bar.invalidate();
        detail.setText(Math.round(bar.value * 100f) + "%");
    }

    void showDone(Uri uri) {
        title.setText("Pronto! Salvo em Filmes/VectorMotion");
        detail.setText("Vídeo vertical 9:16 • 30 fps");
        bar.value = 1f;
        bar.invalidate();
        final PillButton tiktok = new PillButton(getContext(), "Enviar ao TikTok", true);
        tiktok.setOnClickListener(v -> actions.onTikTok(uri));
        final PillButton share = new PillButton(getContext(), "Outros apps", false);
        share.setOnClickListener(v -> actions.onShare(uri));
        final PillButton close = new PillButton(getContext(), "Fechar", false);
        close.setOnClickListener(v -> actions.onClose());
        showButtons(tiktok, share, close);
    }

    void showError(String msg) {
        title.setText("Ops");
        detail.setText(msg);
        final PillButton close = new PillButton(getContext(), "Fechar", false);
        close.setOnClickListener(v -> actions.onClose());
        showButtons(close);
    }
}
