package app.vectormotion.studio;

import android.app.Application;

/** Instala o registro de travamentos o mais cedo possível (antes de qualquer Activity). */
public class VectorMotionApp extends Application {
    @Override
    public void onCreate() {
        super.onCreate();
        CrashReporter.install(this);
    }
}
