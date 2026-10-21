package app.vectormotion.studio;

import android.annotation.SuppressLint;
import android.content.Context;
import android.graphics.SurfaceTexture;
import android.hardware.camera2.CameraAccessException;
import android.hardware.camera2.CameraCaptureSession;
import android.hardware.camera2.CameraCharacteristics;
import android.hardware.camera2.CameraDevice;
import android.hardware.camera2.CameraManager;
import android.hardware.camera2.CaptureRequest;
import android.hardware.camera2.params.StreamConfigurationMap;
import android.os.Handler;
import android.os.HandlerThread;
import android.util.Size;
import android.view.Surface;

import java.util.Collections;

/** Camera2 traseira, prévia contínua em 16:9 (exibida em 9:16 retrato) com trava de exposição para stop-motion. */
final class CameraController {
    interface Listener {
        void onReady();
        void onError(String message);
    }

    private final Context ctx;
    private final Listener listener;
    private final Handler main;
    private HandlerThread thread;
    private Handler handler;
    private CameraDevice device;
    private CameraCaptureSession session;
    private CaptureRequest.Builder builder;
    private Surface surface;
    private boolean aeLock;
    private boolean closed = true;

    CameraController(Context ctx, Handler main, Listener l) {
        this.ctx = ctx;
        this.main = main;
        this.listener = l;
    }

    /** Escolhe o maior tamanho 16:9 até 1920 de largura (preview em 1080x1920 após rotação). */
    private static Size pickSize(StreamConfigurationMap map) {
        final Size[] sizes = map.getOutputSizes(SurfaceTexture.class);
        Size best = null;
        for (Size s : sizes) {
            if (s.getWidth() > 1920) continue;
            if (s.getWidth() * 9 != s.getHeight() * 16) continue;
            if (best == null || s.getWidth() > best.getWidth()) best = s;
        }
        if (best != null) return best;
        for (Size s : sizes) {
            if (s.getWidth() > 1920) continue;
            if (best == null || s.getWidth() * s.getHeight() > best.getWidth() * best.getHeight()) best = s;
        }
        return best != null ? best : sizes[0];
    }

    @SuppressLint("MissingPermission")  // a permissão é checada pela Activity antes de abrir
    void open(SurfaceTexture st) {
        if (!closed) return;
        closed = false;
        thread = new HandlerThread("camera");
        thread.start();
        handler = new Handler(thread.getLooper());
        try {
            final CameraManager mgr = (CameraManager) ctx.getSystemService(Context.CAMERA_SERVICE);
            String id = null;
            for (String cid : mgr.getCameraIdList()) {
                final Integer facing = mgr.getCameraCharacteristics(cid).get(CameraCharacteristics.LENS_FACING);
                if (facing != null && facing == CameraCharacteristics.LENS_FACING_BACK) {
                    id = cid;
                    break;
                }
            }
            if (id == null && mgr.getCameraIdList().length > 0) id = mgr.getCameraIdList()[0];
            if (id == null) {
                fail("Nenhuma câmera encontrada");
                return;
            }
            final StreamConfigurationMap map = mgr.getCameraCharacteristics(id)
                    .get(CameraCharacteristics.SCALER_STREAM_CONFIGURATION_MAP);
            if (map == null) {
                fail("Câmera sem configuração de vídeo");
                return;
            }
            final Size size = pickSize(map);
            st.setDefaultBufferSize(size.getWidth(), size.getHeight());
            surface = new Surface(st);
            mgr.openCamera(id, new CameraDevice.StateCallback() {
                @Override
                public void onOpened(CameraDevice d) {
                    if (closed) {
                        d.close();
                        return;
                    }
                    device = d;
                    startSession();
                }

                @Override
                public void onDisconnected(CameraDevice d) {
                    d.close();
                    fail("Câmera desconectada");
                }

                @Override
                public void onError(CameraDevice d, int error) {
                    d.close();
                    fail("Erro da câmera (" + error + ")");
                }
            }, handler);
        } catch (CameraAccessException | SecurityException | IllegalArgumentException e) {
            fail("Não foi possível abrir a câmera");
        }
    }

    private void startSession() {
        try {
            builder = device.createCaptureRequest(CameraDevice.TEMPLATE_PREVIEW);
            builder.addTarget(surface);
            builder.set(CaptureRequest.CONTROL_AF_MODE, CaptureRequest.CONTROL_AF_MODE_CONTINUOUS_PICTURE);
            builder.set(CaptureRequest.CONTROL_AE_LOCK, aeLock);
            builder.set(CaptureRequest.CONTROL_AWB_LOCK, aeLock);
            device.createCaptureSession(Collections.singletonList(surface), new CameraCaptureSession.StateCallback() {
                @Override
                public void onConfigured(CameraCaptureSession s) {
                    if (closed) {
                        s.close();
                        return;
                    }
                    session = s;
                    applyRepeating();
                    main.post(listener::onReady);
                }

                @Override
                public void onConfigureFailed(CameraCaptureSession s) {
                    fail("Falha ao configurar a câmera");
                }
            }, handler);
        } catch (CameraAccessException | IllegalStateException e) {
            fail("Falha ao iniciar a prévia");
        }
    }

    private void applyRepeating() {
        try {
            if (session != null && builder != null) session.setRepeatingRequest(builder.build(), null, handler);
        } catch (CameraAccessException | IllegalStateException e) {
            // câmera fechando: ignora
        }
    }

    /** Trava exposição e balanço de branco para evitar "piscar" entre frames do stop-motion. */
    void setAeLock(boolean lock) {
        aeLock = lock;
        if (handler == null) return;
        handler.post(() -> {
            if (builder == null) return;
            builder.set(CaptureRequest.CONTROL_AE_LOCK, lock);
            builder.set(CaptureRequest.CONTROL_AWB_LOCK, lock);
            applyRepeating();
        });
    }

    private void fail(String msg) {
        main.post(() -> listener.onError(msg));
        close();
    }

    void close() {
        closed = true;
        try {
            if (session != null) session.close();
        } catch (RuntimeException ignored) {
            // já fechada
        }
        try {
            if (device != null) device.close();
        } catch (RuntimeException ignored) {
            // já fechada
        }
        if (surface != null) surface.release();
        session = null;
        device = null;
        builder = null;
        surface = null;
        if (thread != null) {
            thread.quitSafely();
            thread = null;
            handler = null;
        }
    }
}
