package app.vectormotion.studio;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.ClipData;
import android.content.Context;
import android.content.Intent;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.Rect;
import android.graphics.RectF;
import android.graphics.SurfaceTexture;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.Handler;
import android.os.Looper;
import android.os.StatFs;
import android.view.Gravity;
import android.view.HapticFeedbackConstants;
import android.view.TextureView;
import android.view.View;
import android.view.WindowInsets;
import android.widget.FrameLayout;
import android.widget.HorizontalScrollView;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.SeekBar;
import android.widget.TextView;
import android.widget.Toast;

import java.io.File;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Tela principal do estúdio: câmera 9:16, onion skin, linha do tempo, efeitos CGI e exportação. */
final class StudioView extends FrameLayout implements TextureView.SurfaceTextureListener, CameraController.Listener {
    private static final int CAP_W = 1080, CAP_H = 1920;
    private static final int[] FPS_STEPS = {6, 8, 10, 12, 15, 24};
    private static final String[] FX_NAMES = {"Sem FX", "Herói", "Energia", "Cósmico", "Noir"};
    private static final long MIN_FREE_BYTES = 150L * 1024 * 1024;

    /** Painel que mantém proporção 9:16 dentro do espaço disponível. */
    private static final class Panel extends FrameLayout {
        Panel(Context c) {
            super(c);
        }

        @Override
        protected void onMeasure(int wSpec, int hSpec) {
            final int maxW = MeasureSpec.getSize(wSpec), maxH = MeasureSpec.getSize(hSpec);
            final int w = Math.min(maxW, maxH * 9 / 16);
            final int h = w * 16 / 9;
            setMeasuredDimension(w, h);
            measureChildren(MeasureSpec.makeMeasureSpec(w, MeasureSpec.EXACTLY), MeasureSpec.makeMeasureSpec(h, MeasureSpec.EXACTLY));
        }
    }

    /** Miniatura da linha do tempo. */
    private static final class Thumb extends View {
        private Bitmap bmp;
        private final int index;
        private int hold = 1;
        boolean selected;
        boolean playing;
        private final Paint p = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final Path path = new Path();
        private final RectF r = new RectF();
        private final Rect src = new Rect();
        private final Rect dst = new Rect();

        Thumb(Context c, int index, int hold) {
            super(c);
            this.index = index;
            this.hold = hold;
            p.setTypeface(Theme.bold());
            setClickable(true);
            setContentDescription("Frame " + (index + 1));
        }

        void setBitmap(Bitmap b) {
            bmp = b;
            invalidate();
        }

        @Override
        protected void onDraw(Canvas c) {
            final float w = getWidth(), h = getHeight();
            if (bmp != null) {
                final float scale = Math.max(w / bmp.getWidth(), h / bmp.getHeight());
                final int sw = (int) (w / scale), sh = (int) (h / scale);
                src.set((bmp.getWidth() - sw) / 2, (bmp.getHeight() - sh) / 2, (bmp.getWidth() + sw) / 2, (bmp.getHeight() + sh) / 2);
                dst.set(0, 0, (int) w, (int) h);
                c.drawBitmap(bmp, src, dst, null);
            } else {
                c.drawColor(Theme.PANEL2);
            }
            p.setStyle(Paint.Style.FILL);
            p.setColor(0xAA000000);
            c.drawRect(0, h - Theme.dp(16), w, h, p);
            p.setColor(Theme.TEXT);
            p.setTextSize(Theme.dp(10));
            c.drawText(String.valueOf(index + 1), Theme.dp(4), h - Theme.dp(4), p);
            if (hold > 1) {
                p.setColor(Theme.GOLD);
                c.drawText("x" + hold, w - Theme.dp(20), h - Theme.dp(4), p);
            }
            if (selected || playing) {
                r.set(Theme.dp(1.5f), Theme.dp(1.5f), w - Theme.dp(1.5f), h - Theme.dp(1.5f));
                p.setStyle(Paint.Style.STROKE);
                p.setStrokeWidth(Theme.dp(3));
                p.setColor(selected ? Theme.RED : Theme.GOLD);
                p.setShadowLayer(Theme.dp(6), 0, 0, p.getColor());
                c.drawRect(r, p);
                p.clearShadowLayer();
            }
        }
    }

    private final Activity act;
    private final Handler main = new Handler(Looper.getMainLooper());
    private final Project project;
    private final FrameRenderer renderer = new FrameRenderer();
    private final ExecutorService io = Executors.newSingleThreadExecutor();
    private final ExecutorService thumbExec = Executors.newFixedThreadPool(2);
    private final CameraController camera;

    private final TextureView texture;
    private final ImageView onionView;
    private final ImageView playView;
    private final View flash;
    private final HudOverlay hud;
    private final Panel panel;
    private final LinearLayout topBar;
    private final LinearLayout side;
    private final LinearLayout bottom;
    private final TextView counter;
    private final LinearLayout strip;
    private final HorizontalScrollView stripScroll;
    private final LinearLayout editRow;
    private final TextView holdLabel;
    private final LinearLayout fxPanel;
    private final HudButton onionBtn, lockBtn, fxBtn, fpsBtn, newBtn, undoBtn, playBtn;
    private final ReactorButton reactor;
    private final HudButton[] fxChips = new HudButton[FX_NAMES.length];

    private ExportOverlay exportOverlay;
    private Exporter exporter;

    private boolean resumed;
    private boolean cameraReady;
    private boolean gotFrame;
    private boolean onion = true;
    private boolean aeLock = true;
    private boolean fxOpen;
    private boolean newArmed;
    private volatile boolean playing;
    private int selected = -1;
    private volatile int fxPreset = NativeCore.FX_HERO;
    private volatile float fxIntensity = 0.8f;
    private int saving;
    private Thread playThread;

    StudioView(Activity a) {
        super(a);
        act = a;
        project = new Project(a);
        camera = new CameraController(a, main, this);
        setBackgroundColor(Theme.BG);

        // ---- câmera + camadas ----
        panel = new Panel(a);
        final ImageView placeholder = new ImageView(a);   // arte de herói até a câmera entregar o 1º frame
        placeholder.setScaleType(ImageView.ScaleType.CENTER_CROP);
        placeholder.setImageDrawable(a.getDrawable(R.drawable.hero_scene));
        placeholder.setAlpha(0.55f);
        panel.addView(placeholder, new LayoutParams(-1, -1));
        texture = new TextureView(a);
        texture.setSurfaceTextureListener(this);
        panel.addView(texture, new LayoutParams(-1, -1));
        onionView = new ImageView(a);
        onionView.setScaleType(ImageView.ScaleType.FIT_XY);
        onionView.setAlpha(0.45f);
        onionView.setVisibility(GONE);
        panel.addView(onionView, new LayoutParams(-1, -1));
        playView = new ImageView(a);
        playView.setScaleType(ImageView.ScaleType.FIT_XY);
        playView.setBackgroundColor(Theme.BG);
        playView.setVisibility(GONE);
        panel.addView(playView, new LayoutParams(-1, -1));
        hud = new HudOverlay(a);
        panel.addView(hud, new LayoutParams(-1, -1));
        flash = new View(a);
        flash.setBackgroundColor(0xFFFFFFFF);
        flash.setAlpha(0f);
        flash.setClickable(false);
        panel.addView(flash, new LayoutParams(-1, -1));
        addView(panel, new LayoutParams(-1, -1, Gravity.TOP | Gravity.CENTER_HORIZONTAL));

        // ---- barra superior ----
        topBar = new LinearLayout(a);
        topBar.setOrientation(LinearLayout.HORIZONTAL);
        topBar.setGravity(Gravity.CENTER_VERTICAL);
        topBar.setPadding(Theme.dpi(14), 0, Theme.dpi(14), 0);
        final TextView title = Theme.label(a, "VECTOR MOTION", 17, Theme.TEXT);
        title.setTypeface(Theme.display());
        title.setPadding(Theme.dpi(12), Theme.dpi(5), Theme.dpi(16), Theme.dpi(5));
        title.setBackground(new SlantDrawable(Theme.RED));
        topBar.addView(title, new LinearLayout.LayoutParams(-2, -2));
        counter = Theme.label(a, "", 11, Theme.GOLD);
        counter.setGravity(Gravity.CENTER);
        topBar.addView(counter, new LinearLayout.LayoutParams(0, -2, 1f));
        final HudButton export = new HudButton(a, Icons.EXPORT, "Exportar");
        export.setOnClickListener(v -> startExport());
        topBar.addView(export, new LinearLayout.LayoutParams(Theme.dpi(66), Theme.dpi(50)));
        addView(topBar, new LayoutParams(-1, Theme.dpi(56), Gravity.TOP));

        // ---- coluna lateral de ferramentas ----
        side = new LinearLayout(a);
        side.setOrientation(LinearLayout.VERTICAL);
        onionBtn = tool(Icons.ONION, "Onion");
        lockBtn = tool(Icons.LOCK, "Trava");
        fxBtn = tool(Icons.FX, "CGI");
        fpsBtn = tool(Icons.PLAY, "");
        newBtn = tool(Icons.NEW, "Novo");
        onionBtn.setActive(true);
        lockBtn.setActive(true);
        onionBtn.setOnClickListener(v -> toggleOnion());
        lockBtn.setOnClickListener(v -> toggleLock());
        fxBtn.setOnClickListener(v -> toggleFx());
        fpsBtn.setOnClickListener(v -> cycleFps());
        newBtn.setOnClickListener(v -> newProject());
        final LayoutParams sp = new LayoutParams(Theme.dpi(58), -2, Gravity.TOP | Gravity.END);
        sp.rightMargin = Theme.dpi(10);
        addView(side, sp);

        // ---- bloco inferior ----
        bottom = new LinearLayout(a);
        bottom.setOrientation(LinearLayout.VERTICAL);
        final GradientDrawable scrim = new GradientDrawable(GradientDrawable.Orientation.TOP_BOTTOM, new int[]{0x00000000, 0xEE05060A, 0xFF05060A});
        bottom.setBackground(scrim);

        fxPanel = new LinearLayout(a);
        fxPanel.setOrientation(LinearLayout.VERTICAL);
        fxPanel.setVisibility(GONE);
        final LinearLayout chips = new LinearLayout(a);
        chips.setOrientation(LinearLayout.HORIZONTAL);
        chips.setGravity(Gravity.CENTER);
        for (int i = 0; i < FX_NAMES.length; i++) {
            final int preset = i;
            final HudButton chip = new HudButton(a, Icons.FX, FX_NAMES[i]);
            fxChips[i] = chip;
            chip.setOnClickListener(v -> setFx(preset));
            final LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(0, Theme.dpi(50), 1f);
            lp.leftMargin = lp.rightMargin = Theme.dpi(2);
            chips.addView(chip, lp);
        }
        fxPanel.addView(chips, new LinearLayout.LayoutParams(-1, -2));
        final SeekBar seek = new SeekBar(a);
        seek.setMax(100);
        seek.setProgress(Math.round(fxIntensity * 100));
        seek.setProgressTintList(android.content.res.ColorStateList.valueOf(Theme.RED));
        seek.setThumbTintList(android.content.res.ColorStateList.valueOf(Theme.GOLD));
        seek.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
            @Override
            public void onProgressChanged(SeekBar s, int progress, boolean fromUser) {
                if (fromUser) {
                    fxIntensity = progress / 100f;
                    refreshSelectedPreview();
                }
            }

            @Override
            public void onStartTrackingTouch(SeekBar s) {}

            @Override
            public void onStopTrackingTouch(SeekBar s) {}
        });
        final LinearLayout.LayoutParams seekLp = new LinearLayout.LayoutParams(-1, Theme.dpi(32));
        seekLp.leftMargin = seekLp.rightMargin = Theme.dpi(8);
        fxPanel.addView(seek, seekLp);
        final TextView fxHint = Theme.label(a, "Efeito aplicado na reprodução e na exportação", 9, Theme.MUTED);
        fxPanel.addView(fxHint, new LinearLayout.LayoutParams(-1, -2));
        bottom.addView(fxPanel, new LinearLayout.LayoutParams(-1, -2));

        editRow = new LinearLayout(a);
        editRow.setOrientation(LinearLayout.HORIZONTAL);
        editRow.setGravity(Gravity.CENTER);
        editRow.setVisibility(GONE);
        editRow.addView(small(Icons.LEFT, "Antes", v -> moveSelected(-1)));
        editRow.addView(small(Icons.RIGHT, "Depois", v -> moveSelected(1)));
        editRow.addView(small(Icons.COPY, "Copiar", v -> duplicateSelected()));
        editRow.addView(small(Icons.MINUS, "", v -> holdSelected(-1)));
        holdLabel = Theme.label(a, "x1", 16, Theme.GOLD);
        editRow.addView(holdLabel, new LinearLayout.LayoutParams(Theme.dpi(40), Theme.dpi(44)));
        editRow.addView(small(Icons.PLUS, "", v -> holdSelected(1)));
        editRow.addView(small(Icons.TRASH, "Apagar", v -> deleteSelected()));
        editRow.addView(small(Icons.CLOSE, "Fechar", v -> select(-1)));
        bottom.addView(editRow, new LinearLayout.LayoutParams(-1, -2));

        stripScroll = new HorizontalScrollView(a);
        stripScroll.setHorizontalScrollBarEnabled(false);
        strip = new LinearLayout(a);
        strip.setOrientation(LinearLayout.HORIZONTAL);
        strip.setPadding(Theme.dpi(10), Theme.dpi(4), Theme.dpi(10), Theme.dpi(4));
        stripScroll.addView(strip, new FrameLayout.LayoutParams(-2, -1));
        bottom.addView(stripScroll, new LinearLayout.LayoutParams(-1, Theme.dpi(92)));

        final LinearLayout controls = new LinearLayout(a);
        controls.setOrientation(LinearLayout.HORIZONTAL);
        controls.setGravity(Gravity.CENTER_VERTICAL);
        undoBtn = new HudButton(a, Icons.UNDO, "Desfazer");
        undoBtn.setOnClickListener(v -> undoLast());
        reactor = new ReactorButton(a);
        reactor.setEnabled(false);
        reactor.setOnClickListener(v -> capture());
        playBtn = new HudButton(a, Icons.PLAY, "Reproduzir");
        playBtn.setOnClickListener(v -> togglePlay());
        controls.addView(undoBtn, new LinearLayout.LayoutParams(0, Theme.dpi(56), 1f));
        controls.addView(reactor, new LinearLayout.LayoutParams(-2, -2));
        controls.addView(playBtn, new LinearLayout.LayoutParams(0, Theme.dpi(56), 1f));
        ((LinearLayout.LayoutParams) undoBtn.getLayoutParams()).leftMargin = Theme.dpi(18);
        ((LinearLayout.LayoutParams) undoBtn.getLayoutParams()).rightMargin = Theme.dpi(12);
        ((LinearLayout.LayoutParams) playBtn.getLayoutParams()).leftMargin = Theme.dpi(12);
        ((LinearLayout.LayoutParams) playBtn.getLayoutParams()).rightMargin = Theme.dpi(18);
        bottom.addView(controls, new LinearLayout.LayoutParams(-1, -2));
        addView(bottom, new LayoutParams(-1, -2, Gravity.BOTTOM));

        setOnApplyWindowInsetsListener((v, insets) -> {
            applyInsets(insets.getSystemWindowInsetTop(), insets.getSystemWindowInsetBottom());
            return insets;
        });
        applyInsets(0, 0);

        updateFxChips();
        updateFpsLabel();
        rebuildStrip();
        updateCounter();
    }

    // ---------------------------------------------------------------- layout

    private void applyInsets(int top, int bottomInset) {
        final int bar = Theme.dpi(56);
        ((LayoutParams) topBar.getLayoutParams()).topMargin = top;
        ((LayoutParams) panel.getLayoutParams()).topMargin = top + bar;
        ((LayoutParams) side.getLayoutParams()).topMargin = top + bar + Theme.dpi(12);
        bottom.setPadding(0, Theme.dpi(18), 0, bottomInset + Theme.dpi(10));
        requestLayout();
    }

    private HudButton tool(int icon, String label) {
        final HudButton b = new HudButton(act, icon, label);
        final LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(-1, Theme.dpi(54));
        lp.bottomMargin = Theme.dpi(8);
        side.addView(b, lp);
        return b;
    }

    private HudButton small(int icon, String label, OnClickListener l) {
        final HudButton b = new HudButton(act, icon, label);
        b.setOnClickListener(l);
        final LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(Theme.dpi(52), Theme.dpi(44));
        lp.leftMargin = lp.rightMargin = Theme.dpi(2);
        b.setLayoutParams(lp);
        return b;
    }

    /** Fundo vermelho inclinado do título. */
    private static final class SlantDrawable extends android.graphics.drawable.Drawable {
        private final Paint p = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final Path path = new Path();
        private final RectF r = new RectF();

        SlantDrawable(int color) {
            p.setColor(color);
        }

        @Override
        public void draw(Canvas c) {
            r.set(getBounds());
            c.drawPath(Theme.slant(r, Theme.dp(10), path), p);
        }

        @Override
        public void setAlpha(int a) {
            p.setAlpha(a);
        }

        @Override
        public void setColorFilter(android.graphics.ColorFilter cf) {
            p.setColorFilter(cf);
        }

        @Override
        public int getOpacity() {
            return android.graphics.PixelFormat.TRANSLUCENT;
        }
    }

    // ---------------------------------------------------------------- ciclo de vida

    void onResume() {
        resumed = true;
        if (texture.isAvailable()) openCamera(texture.getSurfaceTexture());
    }

    void onPause() {
        resumed = false;
        stopPlayback();
        cancelExport();
        camera.close();
        cameraReady = false;
        gotFrame = false;
        reactor.setEnabled(false);
    }

    void onDestroy() {
        stopPlayback();
        cancelExport();
        camera.close();
        io.shutdown();
        thumbExec.shutdownNow();
        renderer.clear();
    }

    /** @return true se consumiu o botão voltar. */
    boolean onBack() {
        if (exportOverlay != null) {
            return true;
        }
        if (playing) {
            stopPlayback();
            return true;
        }
        if (selected >= 0) {
            select(-1);
            return true;
        }
        if (fxOpen) {
            toggleFx();
            return true;
        }
        return false;
    }

    private void openCamera(SurfaceTexture st) {
        if (st != null) camera.open(st);
    }

    @Override
    public void onSurfaceTextureAvailable(SurfaceTexture st, int w, int h) {
        if (resumed) openCamera(st);
    }

    @Override
    public void onSurfaceTextureSizeChanged(SurfaceTexture st, int w, int h) {}

    @Override
    public boolean onSurfaceTextureDestroyed(SurfaceTexture st) {
        camera.close();
        cameraReady = false;
        return true;
    }

    @Override
    public void onSurfaceTextureUpdated(SurfaceTexture st) {
        if (cameraReady && !gotFrame) {
            gotFrame = true;
            reactor.setEnabled(true);
        }
    }

    @Override
    public void onReady() {
        cameraReady = true;
        if (aeLock) main.postDelayed(() -> camera.setAeLock(true), 1200);
    }

    @Override
    public void onError(String message) {
        cameraReady = false;
        reactor.setEnabled(false);
        toast(message);
    }

    // ---------------------------------------------------------------- captura

    private void capture() {
        if (!cameraReady || !gotFrame || playing || exportOverlay != null) return;
        if (project.count() + saving >= Project.MAX_FRAMES) {
            toast("Limite de " + Project.MAX_FRAMES + " frames atingido.");
            return;
        }
        if (new StatFs(act.getFilesDir().getPath()).getAvailableBytes() < MIN_FREE_BYTES) {
            toast("Espaço insuficiente no aparelho.");
            return;
        }
        if (selected >= 0) select(-1);
        final Bitmap bm = texture.getBitmap(CAP_W, CAP_H);
        if (bm == null) {
            toast("Não foi possível capturar a imagem.");
            return;
        }
        reactor.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY);
        flash.animate().cancel();
        flash.setAlpha(0.7f);
        flash.animate().alpha(0f).setDuration(220).start();

        final Bitmap ghost = Bitmap.createScaledBitmap(bm, CAP_W / 2, CAP_H / 2, true);
        final Bitmap ghostMutable = ghost.isMutable() ? ghost : ghost.copy(Bitmap.Config.ARGB_8888, true);
        NativeCore.onionGhost(ghostMutable, Theme.CYAN & 0xFFFFFF, 0.9f);
        onionView.setImageBitmap(ghostMutable);
        onionView.setVisibility(onion ? VISIBLE : GONE);

        saving++;
        io.execute(() -> {
            String error = null;
            try {
                project.addFrame(bm);
            } catch (java.io.IOException e) {
                error = "Falha ao salvar o frame.";
            }
            bm.recycle();
            final String err = error;
            main.post(() -> {
                saving--;
                if (err != null) {
                    toast(err);
                } else {
                    appendThumb(project.count() - 1);
                    updateCounter();
                }
            });
        });
    }

    private void undoLast() {
        if (playing) return;
        final int n = project.count();
        if (n == 0) return;
        project.remove(n - 1);
        if (selected >= n - 1) selected = -1;
        rebuildStrip();
        updateCounter();
        refreshOnionFromLast();
        select(-1);
    }

    /** Recria o fantasma do onion skin a partir do último frame que sobrou. */
    private void refreshOnionFromLast() {
        final int n = project.count();
        if (n == 0) {
            onionView.setImageDrawable(null);
            onionView.setVisibility(GONE);
            return;
        }
        final String name = project.nameAt(n - 1);
        thumbExec.execute(() -> {
            final Bitmap b = FrameRenderer.decode(project.file(name), 2);
            if (b == null) return;
            NativeCore.onionGhost(b, Theme.CYAN & 0xFFFFFF, 0.9f);
            main.post(() -> {
                onionView.setImageBitmap(b);
                onionView.setVisibility(onion ? VISIBLE : GONE);
            });
        });
    }

    // ---------------------------------------------------------------- ferramentas

    private void toggleOnion() {
        onion = !onion;
        onionBtn.setActive(onion);
        onionView.setVisibility(onion && onionView.getDrawable() != null ? VISIBLE : GONE);
    }

    private void toggleLock() {
        aeLock = !aeLock;
        lockBtn.setActive(aeLock);
        camera.setAeLock(aeLock);
        toast(aeLock ? "Exposição travada (sem piscar entre frames)" : "Exposição automática");
    }

    private void toggleFx() {
        fxOpen = !fxOpen;
        fxPanel.setVisibility(fxOpen ? VISIBLE : GONE);
        fxBtn.setActive(fxOpen);
    }

    private void setFx(int preset) {
        fxPreset = preset;
        updateFxChips();
        refreshSelectedPreview();
    }

    private void updateFxChips() {
        for (int i = 0; i < fxChips.length; i++) fxChips[i].setActive(i == fxPreset);
    }

    private void cycleFps() {
        final int cur = project.fps();
        int next = FPS_STEPS[0];
        for (int i = 0; i < FPS_STEPS.length; i++) {
            if (FPS_STEPS[i] == cur) {
                next = FPS_STEPS[(i + 1) % FPS_STEPS.length];
                break;
            }
        }
        project.setFps(next);
        updateFpsLabel();
        updateCounter();
    }

    private void updateFpsLabel() {
        fpsBtn.setIconText(String.valueOf(project.fps()));
        fpsBtn.setLabel("FPS");
    }

    private void newProject() {
        if (playing) return;
        if (project.count() == 0) return;
        if (!newArmed) {
            newArmed = true;
            newBtn.setActive(true);
            newBtn.setLabel("Confirmar");
            main.postDelayed(() -> {
                newArmed = false;
                newBtn.setActive(false);
                newBtn.setLabel("Novo");
            }, 3000);
            return;
        }
        newArmed = false;
        newBtn.setActive(false);
        newBtn.setLabel("Novo");
        select(-1);
        project.clear();
        renderer.clear();
        onionView.setImageDrawable(null);
        onionView.setVisibility(GONE);
        rebuildStrip();
        updateCounter();
    }

    // ---------------------------------------------------------------- linha do tempo

    private void rebuildStrip() {
        strip.removeAllViews();
        final int n = project.count();
        for (int i = 0; i < n; i++) appendThumbView(i);
    }

    private void appendThumb(int index) {
        appendThumbView(index);
        stripScroll.post(() -> stripScroll.fullScroll(View.FOCUS_RIGHT));
    }

    private void appendThumbView(int i) {
        final String name = project.nameAt(i);
        final Thumb t = new Thumb(act, i, project.holdAt(i));
        t.selected = (i == selected);
        t.setOnClickListener(v -> select(i));
        final LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(Theme.dpi(46), Theme.dpi(82));
        lp.rightMargin = Theme.dpi(5);
        strip.addView(t, lp);
        thumbExec.execute(() -> {
            final Bitmap b = renderer.thumb(project.file(name));
            if (b != null) main.post(() -> t.setBitmap(b));
        });
    }

    private void select(int index) {
        if (playing) stopPlayback();
        selected = (index >= 0 && index < project.count()) ? index : -1;
        for (int i = 0; i < strip.getChildCount(); i++) {
            final Thumb t = (Thumb) strip.getChildAt(i);
            t.selected = (i == selected);
            t.invalidate();
        }
        editRow.setVisibility(selected >= 0 ? VISIBLE : GONE);
        if (selected < 0) {
            playView.setVisibility(GONE);
            hud.setTag("AO VIVO", Theme.RED);
            return;
        }
        holdLabel.setText("x" + project.holdAt(selected));
        hud.setTag("FRAME " + (selected + 1), Theme.GOLD);
        refreshSelectedPreview();
    }

    private void refreshSelectedPreview() {
        final int idx = selected;
        if (idx < 0 || idx >= project.count()) return;
        final File f = project.file(project.nameAt(idx));
        final int preset = fxPreset;
        final float inten = fxIntensity;
        thumbExec.execute(() -> {
            final Bitmap b = renderer.preview(f, preset, inten, 2);
            if (b != null) main.post(() -> {
                if (selected == idx && !playing) {
                    playView.setImageBitmap(b);
                    playView.setVisibility(VISIBLE);
                }
            });
        });
    }

    private void moveSelected(int delta) {
        final int to = selected + delta;
        if (selected < 0 || to < 0 || to >= project.count()) return;
        if (project.move(selected, to)) {
            selected = to;
            rebuildStrip();
            select(to);
        }
    }

    private void duplicateSelected() {
        if (selected < 0 || project.count() >= Project.MAX_FRAMES) return;
        if (project.duplicate(selected)) {
            final int to = selected + 1;
            rebuildStrip();
            select(to);
            updateCounter();
        }
    }

    private void holdSelected(int delta) {
        if (selected < 0) return;
        if (project.setHold(selected, Math.max(1, project.holdAt(selected) + delta))) {
            holdLabel.setText("x" + project.holdAt(selected));
            rebuildStrip();
            select(selected);
            updateCounter();
        }
    }

    private void deleteSelected() {
        if (selected < 0) return;
        final int idx = selected;
        project.remove(idx);
        rebuildStrip();
        select(-1);
        updateCounter();
        if (idx >= project.count()) refreshOnionFromLast();
    }

    private void updateCounter() {
        final long frames = project.totalFrames();
        final double secs = project.durationUs() / 1_000_000.0;
        counter.setText(String.format(Locale.US, "%d frames • %.1fs", frames, secs));
    }

    // ---------------------------------------------------------------- reprodução

    private void togglePlay() {
        if (playing) {
            stopPlayback();
            return;
        }
        if (project.count() == 0) {
            toast("Capture alguns frames primeiro.");
            return;
        }
        select(-1);
        playing = true;
        playBtn.setActive(true);
        hud.setTag("REPRODUZINDO", Theme.CYAN);
        playThread = new Thread(() -> {
            final long tl = project.cloneTimeline();
            try {
                final long dur = NativeCore.tlDurationUs(tl);
                if (dur <= 0) return;
                long start = System.nanoTime();
                int last = -2;
                while (playing) {
                    long us = (System.nanoTime() - start) / 1000;
                    if (us >= dur) {
                        start = System.nanoTime();  // loop
                        us = 0;
                    }
                    final int idx = NativeCore.tlClipAtUs(tl, us);
                    if (idx >= 0 && idx != last) {
                        last = idx;
                        final Bitmap b = renderer.preview(project.file(NativeCore.tlFile(tl, idx)), fxPreset, fxIntensity, 2);
                        final int shown = idx;
                        if (b != null) main.post(() -> {
                            if (!playing) return;
                            playView.setImageBitmap(b);
                            playView.setVisibility(VISIBLE);
                            highlight(shown);
                        });
                    }
                    try {
                        Thread.sleep(4);
                    } catch (InterruptedException e) {
                        break;
                    }
                }
            } finally {
                NativeCore.tlFree(tl);
            }
        }, "playback");
        playThread.start();
    }

    private void highlight(int idx) {
        for (int i = 0; i < strip.getChildCount(); i++) {
            final Thumb t = (Thumb) strip.getChildAt(i);
            final boolean on = (i == idx);
            if (t.playing != on) {
                t.playing = on;
                t.invalidate();
                if (on) stripScroll.smoothScrollTo(Math.max(0, t.getLeft() - getWidth() / 2), 0);
            }
        }
    }

    private void stopPlayback() {
        if (!playing) return;
        playing = false;
        if (playThread != null) playThread.interrupt();
        playThread = null;
        playBtn.setActive(false);
        playView.setVisibility(GONE);
        highlight(-1);
        hud.setTag("AO VIVO", Theme.RED);
    }

    // ---------------------------------------------------------------- exportação

    private void startExport() {
        if (exportOverlay != null || project.count() == 0) {
            if (project.count() == 0) toast("Capture alguns frames primeiro.");
            return;
        }
        stopPlayback();
        select(-1);
        final Exporter ex = new Exporter(act, project, fxPreset, fxIntensity);
        exporter = ex;
        exportOverlay = new ExportOverlay(act, new ExportOverlay.Actions() {
            @Override
            public void onCancel() {
                ex.cancel();
            }

            @Override
            public void onTikTok(Uri uri) {
                shareVideo(uri, true);
            }

            @Override
            public void onShare(Uri uri) {
                shareVideo(uri, false);
            }

            @Override
            public void onClose() {
                closeExport();
            }
        });
        addView(exportOverlay, new LayoutParams(-1, -1));
        ex.start(new Exporter.Listener() {
            @Override
            public void onProgress(float f) {
                if (exportOverlay != null && exporter == ex) exportOverlay.setProgress(f);
            }

            @Override
            public void onDone(Uri uri) {
                if (exportOverlay != null && exporter == ex) exportOverlay.showDone(uri);
            }

            @Override
            public void onError(String message) {
                if (exportOverlay != null && exporter == ex) exportOverlay.showError(message);
            }
        });
    }

    private void cancelExport() {
        if (exporter != null) exporter.cancel();
    }

    private void closeExport() {
        if (exportOverlay != null) removeView(exportOverlay);
        exportOverlay = null;
        exporter = null;
    }

    private void shareVideo(Uri uri, boolean tiktok) {
        final Intent i = new Intent(Intent.ACTION_SEND);
        i.setType("video/mp4");
        i.putExtra(Intent.EXTRA_STREAM, uri);
        i.setClipData(ClipData.newRawUri("video", uri));
        i.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
        if (tiktok) {
            for (String pkg : new String[]{"com.zhiliaoapp.musically", "com.ss.android.ugc.trill"}) {
                i.setPackage(pkg);
                try {
                    act.startActivity(i);
                    return;
                } catch (ActivityNotFoundException ignored) {
                    // tenta o próximo pacote
                }
            }
            i.setPackage(null);
            toast("TikTok não encontrado: escolha outro app.");
        }
        try {
            act.startActivity(Intent.createChooser(i, "Compartilhar vídeo"));
        } catch (ActivityNotFoundException e) {
            toast("Nenhum app para compartilhar.");
        }
    }

    private void toast(String msg) {
        Toast.makeText(act, msg, Toast.LENGTH_SHORT).show();
    }
}
