package app.vectormotion.studio;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.view.Gravity;
import android.view.View;
import android.view.WindowInsets;
import android.view.WindowInsetsController;
import android.view.WindowManager;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

/**
 * Entrada do app. As permissões (câmera + microfone) são pedidas UMA vez, em um único diálogo, logo na
 * abertura, enquanto a abertura animada roda. Nada mais é pedido depois: o armazenamento usa MediaStore
 * (sem permissão no Android 10).
 */
public class MainActivity extends Activity {
    private static final int REQ = 1;
    private static final String KEY_ASKED = "asked";

    private FrameLayout root;
    private StudioView studio;
    private View denied;
    private SplashView splash;
    private boolean splashDone;
    private boolean asked;
    private boolean pending;   // diálogo de permissão aberto
    private boolean reportMode;   // mostrando o relatório de travamento

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        Theme.init(this);
        // Se a última execução travou, mostra o motivo em vez de abrir (e travar de novo)
        final String report = CrashReporter.pending(this);
        if (report != null) {
            showReport("O app travou na última vez", report);
            return;
        }
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        immersive();
        asked = b != null && b.getBoolean(KEY_ASKED, false);

        root = new FrameLayout(this);
        root.setBackgroundColor(Theme.BG);
        setContentView(root);
        immersive();
        if (Build.VERSION.SDK_INT >= 29) getWindow().setNavigationBarContrastEnforced(false);
        if (Build.VERSION.SDK_INT >= 33) {
            // Alvo API 36: o sistema não chama mais onBackPressed; o voltar chega por este callback
            getOnBackInvokedDispatcher().registerOnBackInvokedCallback(
                    android.window.OnBackInvokedDispatcher.PRIORITY_DEFAULT, this::handleBack);
        }

        splash = new SplashView(this);
        root.addView(splash, new FrameLayout.LayoutParams(-1, -1));
        splash.start(() -> {
            splashDone = true;
            enterIfReady();
        });

        if (!hasCamera() && !asked) {
            asked = true;
            pending = true;
            requestPermissions(new String[]{Manifest.permission.CAMERA, Manifest.permission.RECORD_AUDIO}, REQ);
        }
    }

    private boolean hasCamera() {
        return checkSelfPermission(Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED;
    }

    @Override
    protected void onSaveInstanceState(Bundle out) {
        super.onSaveInstanceState(out);
        out.putBoolean(KEY_ASKED, asked);
    }

    @Override
    public void onRequestPermissionsResult(int code, String[] perms, int[] results) {
        super.onRequestPermissionsResult(code, perms, results);
        pending = false;
        enterIfReady();
    }

    private void enterIfReady() {
        if (reportMode || !splashDone || studio != null || pending) return;   // espera o resultado do diálogo
        if (hasCamera()) {
            if (denied != null) {
                root.removeView(denied);
                denied = null;
            }
            if (!NativeCore.LOADED) {
                showReport("A biblioteca nativa não carregou", CrashReporter.device() + "\n" + NativeCore.LOAD_ERROR);
                return;
            }
            try {
                studio = new StudioView(this);
                root.addView(studio, 0, new FrameLayout.LayoutParams(-1, -1));
                root.removeView(splash);
                studio.onResume();
                studio.requestApplyInsets();
            } catch (Throwable t) {
                studio = null;
                final java.io.StringWriter sw = new java.io.StringWriter();
                t.printStackTrace(new java.io.PrintWriter(sw));
                showReport("Falha ao abrir o estúdio", CrashReporter.device() + "\n" + sw);
            }
        } else if (denied == null) {
            showDenied();
        }
    }

    /** Tela de diagnóstico: texto selecionável + botão de compartilhar, para o usuário me enviar o erro sem computador. */
    private void showReport(String title, String text) {
        reportMode = true;
        final LinearLayout col = new LinearLayout(this);
        col.setOrientation(LinearLayout.VERTICAL);
        col.setBackgroundColor(Theme.BG);
        col.setOnApplyWindowInsetsListener((v, insets) -> {
            int t = 0, bt = 0;
            if (Build.VERSION.SDK_INT >= 30) {
                final android.graphics.Insets i = insets.getInsets(WindowInsets.Type.systemBars() | WindowInsets.Type.displayCutout());
                t = i.top;
                bt = i.bottom;
            }
            v.setPadding(Theme.dpi(16), Theme.dpi(16) + t, Theme.dpi(16), Theme.dpi(16) + bt);
            return insets;
        });
        col.setPadding(Theme.dpi(16), Theme.dpi(48), Theme.dpi(16), Theme.dpi(16));
        final TextView h = Theme.label(this, title, 20, Theme.RED);
        h.setTypeface(Theme.display());
        h.setGravity(Gravity.START);
        col.addView(h, new LinearLayout.LayoutParams(-1, -2));
        final TextView hint = Theme.label(this, "Compartilhe este texto com quem está corrigindo o app.", 11, Theme.GOLD);
        hint.setAllCaps(false);
        hint.setGravity(Gravity.START);
        final LinearLayout.LayoutParams hp = new LinearLayout.LayoutParams(-1, -2);
        hp.topMargin = Theme.dpi(6);
        col.addView(hint, hp);
        final ScrollView sv = new ScrollView(this);
        final TextView body = new TextView(this);
        body.setText(text);
        body.setTextColor(Theme.TEXT);
        body.setTextSize(11);
        body.setTypeface(android.graphics.Typeface.MONOSPACE);
        body.setTextIsSelectable(true);
        sv.addView(body);
        final LinearLayout.LayoutParams sp = new LinearLayout.LayoutParams(-1, 0, 1f);
        sp.topMargin = Theme.dpi(12);
        col.addView(sv, sp);
        final PillButton share = new PillButton(this, "Compartilhar relatório", true);
        share.setOnClickListener(v -> {
            final Intent i = new Intent(Intent.ACTION_SEND);
            i.setType("text/plain");
            i.putExtra(Intent.EXTRA_TEXT, text);
            startActivity(Intent.createChooser(i, "Enviar relatório"));
        });
        final LinearLayout.LayoutParams a = new LinearLayout.LayoutParams(-1, -2);
        a.topMargin = Theme.dpi(10);
        col.addView(share, a);
        final PillButton retry = new PillButton(this, "Tentar abrir de novo", false);
        retry.setOnClickListener(v -> {
            CrashReporter.clear(this);
            recreate();
        });
        col.addView(retry, a);
        setContentView(col);
    }

    private void showDenied() {
        final LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setGravity(Gravity.CENTER);
        box.setBackgroundColor(Theme.BG);
        box.setPadding(Theme.dpi(28), Theme.dpi(28), Theme.dpi(28), Theme.dpi(28));
        final TextView t = Theme.label(this, "Câmera bloqueada", 24, Theme.RED);
        t.setTypeface(Theme.display());
        box.addView(t, new LinearLayout.LayoutParams(-1, -2));
        final TextView d = Theme.label(this, "O Vector Motion precisa da câmera para capturar os frames. Libere nas configurações do app.", 13, Theme.TEXT);
        d.setAllCaps(false);
        final LinearLayout.LayoutParams dp = new LinearLayout.LayoutParams(-1, -2);
        dp.topMargin = Theme.dpi(12);
        box.addView(d, dp);
        final PillButton open = new PillButton(this, "Abrir ajustes", true);
        open.setOnClickListener(v -> startActivity(new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                Uri.fromParts("package", getPackageName(), null))));
        final LinearLayout.LayoutParams op = new LinearLayout.LayoutParams(-1, -2);
        op.topMargin = Theme.dpi(24);
        box.addView(open, op);
        denied = box;
        root.addView(box, new FrameLayout.LayoutParams(-1, -1));
        root.removeView(splash);
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (reportMode) return;
        immersive();
        if (studio != null) studio.onResume();
        else enterIfReady();   // voltou das configurações com a permissão liberada
    }

    @Override
    protected void onPause() {
        if (studio != null) studio.onPause();
        super.onPause();
    }

    @Override
    protected void onDestroy() {
        if (studio != null) studio.onDestroy();
        super.onDestroy();
    }

    @Override
    protected void onActivityResult(int req, int result, Intent data) {
        super.onActivityResult(req, result, data);
        if (studio == null) return;
        final android.net.Uri uri = (result == RESULT_OK && data != null) ? data.getData() : null;
        if (req == StudioView.REQ_MEME) studio.onPickedAudio(uri);
        else if (req == StudioView.REQ_SWAP_VIDEO || req == StudioView.REQ_SWAP_PHOTO) studio.onPickedSwap(req, uri);
    }

    private void handleBack() {
        if (studio != null && studio.onBack()) return;
        finish();
    }

    @Override
    @SuppressWarnings("deprecation")
    public void onBackPressed() {   // Android 10-12 (e 13+ sem o callback)
        if (studio != null && studio.onBack()) return;
        super.onBackPressed();
    }

    @Override
    public void onWindowFocusChanged(boolean hasFocus) {
        super.onWindowFocusChanged(hasFocus);
        if (hasFocus && !reportMode) immersive();
    }

    @SuppressWarnings("deprecation")
    private void immersive() {
        if (Build.VERSION.SDK_INT >= 30) {
            getWindow().setDecorFitsSystemWindows(false);
            final WindowInsetsController c = getWindow().getInsetsController();
            if (c != null) {   // null até a janela existir; é chamado de novo em onResume/foco
                c.hide(WindowInsets.Type.systemBars());
                c.setSystemBarsBehavior(WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE);
            }
        } else {
            getWindow().getDecorView().setSystemUiVisibility(
                    View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                            | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                            | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
                            | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                            | View.SYSTEM_UI_FLAG_FULLSCREEN
                            | View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY);
        }
    }
}
