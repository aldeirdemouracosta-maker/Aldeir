#include "imagetools.h"

#include <QPainter>
#include <QVector>

#include <algorithm>
#include <cmath>

namespace {

// Separable box blur of a float map, used to feather masks.
void boxBlur(QVector<float> &m, int w, int h, int r)
{
    if (r <= 0)
        return;
    QVector<float> tmp(m.size());
    for (int pass = 0; pass < 2; ++pass) { // two passes ≈ triangle filter
        for (int y = 0; y < h; ++y) {
            double acc = 0;
            int n = 0;
            for (int x = -r; x < w; ++x) {
                if (x + r < w) { acc += m[y * w + x + r]; ++n; }
                if (x - r - 1 >= 0) { acc -= m[y * w + x - r - 1]; --n; }
                if (x >= 0) tmp[y * w + x] = float(acc / qMax(1, n));
            }
        }
        for (int x = 0; x < w; ++x) {
            double acc = 0;
            int n = 0;
            for (int y = -r; y < h; ++y) {
                if (y + r < h) { acc += tmp[(y + r) * w + x]; ++n; }
                if (y - r - 1 >= 0) { acc -= tmp[(y - r - 1) * w + x]; --n; }
                if (y >= 0) m[y * w + x] = float(acc / qMax(1, n));
            }
        }
    }
}

struct Rgb {
    float r, g, b;
};

// One level of the inpainting pyramid.
void fillLevel(QVector<Rgb> &px, const QVector<quint8> &hole, int w, int h, int iterations)
{
    QVector<int> idx;
    for (int i = 0; i < hole.size(); ++i)
        if (hole[i])
            idx.append(i);
    for (int it = 0; it < iterations; ++it) {
        for (int i : idx) {
            const int x = i % w, y = i / w;
            Rgb acc{0, 0, 0};
            int n = 0;
            auto add = [&](int xx, int yy) {
                if (xx < 0 || yy < 0 || xx >= w || yy >= h) return;
                const Rgb &p = px[yy * w + xx];
                acc.r += p.r; acc.g += p.g; acc.b += p.b; ++n;
            };
            add(x - 1, y); add(x + 1, y); add(x, y - 1); add(x, y + 1);
            if (n) px[i] = {acc.r / n, acc.g / n, acc.b / n};
        }
    }
}

QVector<Rgb> inpaint(const QVector<Rgb> &src, const QVector<quint8> &hole, int w, int h)
{
    QVector<Rgb> px = src;
    const bool any = std::any_of(hole.begin(), hole.end(), [](quint8 v) { return v != 0; });
    if (!any)
        return px;

    if (w <= 16 || h <= 16) {
        // Coarsest level: start from the mean of the known pixels.
        Rgb mean{0, 0, 0};
        int n = 0;
        for (int i = 0; i < px.size(); ++i) {
            if (!hole[i]) { mean.r += px[i].r; mean.g += px[i].g; mean.b += px[i].b; ++n; }
        }
        if (n) { mean.r /= n; mean.g /= n; mean.b /= n; }
        for (int i = 0; i < px.size(); ++i)
            if (hole[i]) px[i] = mean;
        fillLevel(px, hole, w, h, 200);
        return px;
    }

    // Solve at half resolution, upsample as the initial guess, then refine.
    const int hw = (w + 1) / 2, hh = (h + 1) / 2;
    // A half-res pixel is known if any of its four children is known.
    QVector<Rgb> half(hw * hh, Rgb{0, 0, 0});
    QVector<int> count(hw * hh, 0);
    for (int y = 0; y < h; ++y) {
        for (int x = 0; x < w; ++x) {
            const int i = y * w + x, j = (y / 2) * hw + x / 2;
            if (hole[i])
                continue;
            half[j].r += px[i].r; half[j].g += px[i].g; half[j].b += px[i].b;
            ++count[j];
        }
    }
    QVector<quint8> halfHole(hw * hh, 0);
    for (int j = 0; j < half.size(); ++j) {
        if (count[j]) { half[j].r /= count[j]; half[j].g /= count[j]; half[j].b /= count[j]; }
        else halfHole[j] = 1;
    }
    const QVector<Rgb> filledHalf = inpaint(half, halfHole, hw, hh);
    for (int y = 0; y < h; ++y)
        for (int x = 0; x < w; ++x)
            if (hole[y * w + x]) px[y * w + x] = filledHalf[(y / 2) * hw + x / 2];
    fillLevel(px, hole, w, h, 30);
    return px;
}

} // namespace

QVector<float> ImageTools::maskWeights(const QImage &mask, const QSize &size, int feather)
{
    const QImage m = mask.scaled(size, Qt::IgnoreAspectRatio, Qt::SmoothTransformation).convertToFormat(QImage::Format_ARGB32);
    QVector<float> w(size.width() * size.height(), 0.f);
    const bool hasAlpha = mask.hasAlphaChannel();
    for (int y = 0; y < size.height(); ++y) {
        const QRgb *line = reinterpret_cast<const QRgb *>(m.constScanLine(y));
        for (int x = 0; x < size.width(); ++x) {
            const int v = hasAlpha ? qAlpha(line[x]) : qGray(line[x]);
            w[y * size.width() + x] = v > 16 ? 1.f : 0.f;
        }
    }
    if (feather > 0) {
        // Grow the mask by the feather radius first so the fully replaced core
        // still covers everything that was painted.
        QVector<float> grown = w;
        boxBlur(grown, size.width(), size.height(), feather);
        for (int i = 0; i < w.size(); ++i)
            w[i] = grown[i] > 0.02f ? 1.f : 0.f;
        boxBlur(w, size.width(), size.height(), feather);
    }
    return w;
}

QImage ImageTools::cleanWithPlate(const QImage &frame, const QImage &plate, const QImage &mask, int feather)
{
    const QImage src = frame.convertToFormat(QImage::Format_RGB32);
    const QImage bg = plate.scaled(src.size(), Qt::IgnoreAspectRatio, Qt::SmoothTransformation).convertToFormat(QImage::Format_RGB32);
    const QVector<float> w = maskWeights(mask, src.size(), feather);
    QImage out(src.size(), QImage::Format_RGB32);
    for (int y = 0; y < src.height(); ++y) {
        const QRgb *a = reinterpret_cast<const QRgb *>(src.constScanLine(y));
        const QRgb *b = reinterpret_cast<const QRgb *>(bg.constScanLine(y));
        QRgb *o = reinterpret_cast<QRgb *>(out.scanLine(y));
        for (int x = 0; x < src.width(); ++x) {
            const float k = w[y * src.width() + x];
            o[x] = qRgb(int(qRed(a[x]) * (1 - k) + qRed(b[x]) * k + 0.5f),
                        int(qGreen(a[x]) * (1 - k) + qGreen(b[x]) * k + 0.5f),
                        int(qBlue(a[x]) * (1 - k) + qBlue(b[x]) * k + 0.5f));
        }
    }
    return out;
}

QImage ImageTools::fillMasked(const QImage &frame, const QImage &mask)
{
    const QImage src = frame.convertToFormat(QImage::Format_RGB32);
    const int w = src.width(), h = src.height();
    const QVector<float> weights = maskWeights(mask, src.size(), 1);
    QVector<Rgb> px(w * h);
    QVector<quint8> hole(w * h);
    for (int y = 0; y < h; ++y) {
        const QRgb *line = reinterpret_cast<const QRgb *>(src.constScanLine(y));
        for (int x = 0; x < w; ++x) {
            px[y * w + x] = {float(qRed(line[x])), float(qGreen(line[x])), float(qBlue(line[x]))};
            hole[y * w + x] = weights[y * w + x] > 0.f ? 1 : 0;
        }
    }
    const QVector<Rgb> filled = inpaint(px, hole, w, h);
    QImage out(src.size(), QImage::Format_RGB32);
    for (int y = 0; y < h; ++y) {
        QRgb *o = reinterpret_cast<QRgb *>(out.scanLine(y));
        for (int x = 0; x < w; ++x) {
            const Rgb &p = filled[y * w + x];
            o[x] = qRgb(qBound(0, int(p.r + 0.5f), 255), qBound(0, int(p.g + 0.5f), 255), qBound(0, int(p.b + 0.5f), 255));
        }
    }
    return out;
}

QImage ImageTools::chromaKey(const QImage &frame, const ChromaOptions &o, const QImage &background)
{
    const QImage src = frame.convertToFormat(QImage::Format_ARGB32);
    QImage bg;
    if (!background.isNull()) {
        // Cover the frame, cropping the background's overflow.
        const QImage scaled = background.scaled(src.size(), Qt::KeepAspectRatioByExpanding, Qt::SmoothTransformation);
        bg = scaled.copy((scaled.width() - src.width()) / 2, (scaled.height() - src.height()) / 2, src.width(), src.height())
                 .convertToFormat(QImage::Format_RGB32);
    }

    auto cbcr = [](double r, double g, double b, double &cb, double &cr) {
        cb = (-0.168736 * r - 0.331264 * g + 0.5 * b) / 255.0;
        cr = (0.5 * r - 0.418688 * g - 0.081312 * b) / 255.0;
    };
    double kcb, kcr;
    cbcr(o.key.red(), o.key.green(), o.key.blue(), kcb, kcr);
    // Which channel the screen is made of (green or blue), for spill removal.
    const bool greenScreen = o.key.green() >= o.key.blue();

    QImage out(src.size(), bg.isNull() ? QImage::Format_ARGB32 : QImage::Format_RGB32);
    for (int y = 0; y < src.height(); ++y) {
        const QRgb *a = reinterpret_cast<const QRgb *>(src.constScanLine(y));
        const QRgb *b = bg.isNull() ? nullptr : reinterpret_cast<const QRgb *>(bg.constScanLine(y));
        QRgb *out_ = reinterpret_cast<QRgb *>(out.scanLine(y));
        for (int x = 0; x < src.width(); ++x) {
            double r = qRed(a[x]), g = qGreen(a[x]), bl = qBlue(a[x]);
            double cb, cr;
            cbcr(r, g, bl, cb, cr);
            const double d = std::hypot(cb - kcb, cr - kcr) / 0.7; // normalise to ~0..1
            const double alpha = qBound(0.0, (d - o.tolerance) / qMax(1e-6, o.softness), 1.0);
            if (o.spill) {
                if (greenScreen)
                    g = qMin(g, qMax(r, bl));
                else
                    bl = qMin(bl, qMax(r, g));
            }
            if (b) {
                out_[x] = qRgb(int(r * alpha + qRed(b[x]) * (1 - alpha) + 0.5),
                               int(g * alpha + qGreen(b[x]) * (1 - alpha) + 0.5),
                               int(bl * alpha + qBlue(b[x]) * (1 - alpha) + 0.5));
            } else {
                out_[x] = qRgba(int(r), int(g), int(bl), int(alpha * 255 + 0.5));
            }
        }
    }
    return out;
}
