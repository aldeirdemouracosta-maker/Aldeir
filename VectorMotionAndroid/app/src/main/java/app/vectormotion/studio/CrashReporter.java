package app.vectormotion.studio;

import android.app.ActivityManager;
import android.app.ApplicationExitInfo;
import android.content.Context;
import android.content.SharedPreferences;
import android.os.Build;

import java.io.File;
import java.io.FileOutputStream;
import java.io.PrintWriter;
import java.io.StringWriter;
import java.nio.charset.StandardCharsets;
import java.util.List;

/**
 * Guarda o motivo do último travamento para mostrá-lo na tela na próxima abertura (sem computador/adb).
 * Cobre exceções Java (arquivo gravado pelo handler) e quedas nativas/ANR (ApplicationExitInfo, Android 11+).
 */
final class CrashReporter {
    private static final String FILE = "last_crash.txt";
    private static final String PREFS = "crash";

    private CrashReporter() {}

    static String device() {
        return "Vector Motion " + BuildInfo.VERSION + " • Android " + Build.VERSION.RELEASE + " (API " + Build.VERSION.SDK_INT + ") • "
                + Build.MANUFACTURER + " " + Build.MODEL + " • ABIs " + String.join(",", Build.SUPPORTED_ABIS);
    }

    static void install(Context app) {
        final File f = new File(app.getFilesDir(), FILE);
        final Thread.UncaughtExceptionHandler prev = Thread.getDefaultUncaughtExceptionHandler();
        Thread.setDefaultUncaughtExceptionHandler((t, e) -> {
            try {
                final StringWriter sw = new StringWriter();
                final PrintWriter pw = new PrintWriter(sw);
                pw.println(device());
                pw.println("thread: " + t.getName());
                e.printStackTrace(pw);
                pw.flush();
                try (FileOutputStream out = new FileOutputStream(f)) {
                    out.write(sw.toString().getBytes(StandardCharsets.UTF_8));
                    out.getFD().sync();
                }
            } catch (Throwable ignored) {
                // sem como gravar: segue para o handler padrão
            }
            if (prev != null) prev.uncaughtException(t, e);
            else System.exit(10);
        });
    }

    private static String reasonName(int r) {
        switch (r) {
            case ApplicationExitInfo.REASON_CRASH: return "CRASH (exceção Java)";
            case ApplicationExitInfo.REASON_CRASH_NATIVE: return "CRASH_NATIVE (queda no código nativo)";
            case ApplicationExitInfo.REASON_ANR: return "ANR (app não respondeu)";
            case ApplicationExitInfo.REASON_INITIALIZATION_FAILURE: return "INITIALIZATION_FAILURE";
            default: return null;
        }
    }

    /** Relato pendente (Java ou nativo) ou null se a última execução terminou normalmente. */
    static String pending(Context c) {
        final File f = new File(c.getFilesDir(), FILE);
        if (f.isFile()) {
            try {
                return new String(java.nio.file.Files.readAllBytes(f.toPath()), StandardCharsets.UTF_8);
            } catch (Exception | Error ignored) {
                return device() + "\n(não consegui ler o arquivo do relatório)";
            }
        }
        if (Build.VERSION.SDK_INT >= 30) {
            try {
                final SharedPreferences sp = c.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
                final long seen = sp.getLong("exit_seen", 0);
                final List<ApplicationExitInfo> list = ((ActivityManager) c.getSystemService(Context.ACTIVITY_SERVICE))
                        .getHistoricalProcessExitReasons(c.getPackageName(), 0, 5);
                for (ApplicationExitInfo i : list) {
                    final String name = reasonName(i.getReason());
                    if (name != null && i.getTimestamp() > seen) {
                        return device() + "\nO processo terminou por: " + name + "\nstatus: " + i.getStatus()
                                + "\ndescrição: " + i.getDescription() + "\nhorário: " + new java.util.Date(i.getTimestamp());
                    }
                }
            } catch (RuntimeException ignored) {
                // sem histórico disponível
            }
        }
        return null;
    }

    /** O usuário viu o relato: apaga o arquivo e marca a queda nativa como vista. */
    static void clear(Context c) {
        //noinspection ResultOfMethodCallIgnored
        new File(c.getFilesDir(), FILE).delete();
        c.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().putLong("exit_seen", System.currentTimeMillis()).apply();
    }
}
