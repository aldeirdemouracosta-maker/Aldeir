package app.vectormotion.studio;

import static org.junit.Assert.assertNotNull;

import android.app.Activity;
import android.view.View;
import android.view.ViewGroup;

import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.Robolectric;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.annotation.Config;

/**
 * Abre a MainActivity com o framework real do Android 16 (API 36) e do Android 10 (API 29).
 * Pega travamentos no início do app (como o NPE de getInsetsController no Android 16) antes de gerar o APK.
 */
@RunWith(RobolectricTestRunner.class)
public class LaunchTest {
    private static void abre() {
        final Activity a = Robolectric.buildActivity(MainActivity.class).create().start().resume().visible().get();
        assertNotNull(a);
        final View content = ((ViewGroup) a.findViewById(android.R.id.content)).getChildAt(0);
        assertNotNull("a tela inicial deveria existir", content);
    }

    @Test
    @Config(sdk = 36)
    public void abreNoAndroid16() {
        abre();
    }

    @Test
    @Config(sdk = 29)
    public void abreNoAndroid10() {
        abre();
    }
}
