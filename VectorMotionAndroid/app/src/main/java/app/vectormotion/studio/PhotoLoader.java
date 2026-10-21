package app.vectormotion.studio;

import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Matrix;
import android.media.ExifInterface;
import android.net.Uri;

import java.io.IOException;
import java.io.InputStream;

/** Lê uma foto da galeria respeitando a rotação EXIF, limitada a `maxSide` px, em ARGB_8888 mutável. */
final class PhotoLoader {
    private PhotoLoader() {}

    static Bitmap load(Context ctx, Uri uri, int maxSide) throws IOException {
        final BitmapFactory.Options bounds = new BitmapFactory.Options();
        bounds.inJustDecodeBounds = true;
        try (InputStream in = ctx.getContentResolver().openInputStream(uri)) {
            if (in == null) throw new IOException("Não consegui abrir a foto.");
            BitmapFactory.decodeStream(in, null, bounds);
        }
        if (bounds.outWidth <= 0 || bounds.outHeight <= 0) throw new IOException("Arquivo de foto inválido.");
        int sample = 1;
        while (Math.max(bounds.outWidth, bounds.outHeight) / sample > maxSide * 2) sample *= 2;
        final BitmapFactory.Options o = new BitmapFactory.Options();
        o.inSampleSize = sample;
        o.inPreferredConfig = Bitmap.Config.ARGB_8888;
        o.inMutable = true;
        Bitmap bmp;
        try (InputStream in = ctx.getContentResolver().openInputStream(uri)) {
            bmp = in == null ? null : BitmapFactory.decodeStream(in, null, o);
        } catch (OutOfMemoryError e) {
            throw new IOException("Foto grande demais.");
        }
        if (bmp == null) throw new IOException("Não consegui ler a foto.");

        int rotation = 0;
        try (InputStream in = ctx.getContentResolver().openInputStream(uri)) {
            if (in != null) {
                switch (new ExifInterface(in).getAttributeInt(ExifInterface.TAG_ORIENTATION, ExifInterface.ORIENTATION_NORMAL)) {
                    case ExifInterface.ORIENTATION_ROTATE_90: rotation = 90; break;
                    case ExifInterface.ORIENTATION_ROTATE_180: rotation = 180; break;
                    case ExifInterface.ORIENTATION_ROTATE_270: rotation = 270; break;
                    default: break;
                }
            }
        } catch (IOException ignored) {
            // sem EXIF: usa como está
        }
        final float scale = Math.min(1f, maxSide / (float) Math.max(bmp.getWidth(), bmp.getHeight()));
        if (rotation != 0 || scale < 1f) {
            final Matrix m = new Matrix();
            m.postRotate(rotation);
            m.postScale(scale, scale);
            final Bitmap t = Bitmap.createBitmap(bmp, 0, 0, bmp.getWidth(), bmp.getHeight(), m, true);
            if (t != bmp) bmp.recycle();
            bmp = t;
        }
        if (!bmp.isMutable() || bmp.getConfig() != Bitmap.Config.ARGB_8888) {
            final Bitmap c = bmp.copy(Bitmap.Config.ARGB_8888, true);
            bmp.recycle();
            bmp = c;
        }
        return bmp;
    }
}
