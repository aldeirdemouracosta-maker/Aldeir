#include <QPainter>
#include <QSignalSpy>
#include <QTemporaryDir>
#include <QTest>

#include "frametools.h"
#include "imagetools.h"
#include "projectmanager.h"

class TestImageTools : public QObject
{
    Q_OBJECT

private:
    QTemporaryDir m_home;

    // Smooth "set" background: horizontal and vertical colour gradients.
    static QImage gradient(int w, int h)
    {
        QImage img(w, h, QImage::Format_RGB32);
        for (int y = 0; y < h; ++y)
            for (int x = 0; x < w; ++x)
                img.setPixel(x, y, qRgb(40 + 150 * x / w, 60 + 120 * y / h, 120));
        return img;
    }

    // Transparent mask with an opaque vertical band (the painted wire).
    static QImage bandMask(int w, int h, int x0, int x1)
    {
        QImage m(w, h, QImage::Format_ARGB32);
        m.fill(Qt::transparent);
        QPainter p(&m);
        p.fillRect(QRect(x0, 0, x1 - x0, h), QColor(255, 60, 60, 140));
        return m;
    }

    static int maxDiff(const QImage &a, const QImage &b, const QRect &area)
    {
        int worst = 0;
        for (int y = area.top(); y <= area.bottom(); ++y)
            for (int x = area.left(); x <= area.right(); ++x) {
                const QRgb p = a.pixel(x, y), q = b.pixel(x, y);
                worst = qMax(worst, qMax(qAbs(qRed(p) - qRed(q)), qMax(qAbs(qGreen(p) - qGreen(q)), qAbs(qBlue(p) - qBlue(q)))));
            }
        return worst;
    }

private slots:
    void initTestCase()
    {
        QVERIFY(m_home.isValid());
        qputenv("IA_SMS_HOME", m_home.path().toUtf8());
    }

    void cleanPlateRemovesRig()
    {
        const QImage plate = gradient(200, 120);
        QImage frame = plate.copy();
        QPainter(&frame).fillRect(QRect(98, 0, 5, 120), Qt::black); // support rod
        const QImage out = ImageTools::cleanWithPlate(frame, plate, bandMask(200, 120, 96, 105), 2);
        QVERIFY(maxDiff(out, plate, QRect(96, 0, 9, 120)) <= 2);
        // Far from the mask nothing changes.
        QCOMPARE(maxDiff(out, frame, QRect(0, 0, 80, 120)), 0);
    }

    void fillRemovesThinWire()
    {
        const QImage clean = gradient(240, 160);
        QImage frame = clean.copy();
        QPainter(&frame).fillRect(QRect(120, 0, 3, 160), QColor(20, 20, 20)); // nylon wire
        const QImage out = ImageTools::fillMasked(frame, bandMask(240, 160, 118, 125));
        QVERIFY2(maxDiff(out, clean, QRect(118, 5, 7, 150)) <= 8,
                 qPrintable(QString::number(maxDiff(out, clean, QRect(118, 5, 7, 150)))));
        QCOMPARE(maxDiff(out, frame, QRect(0, 0, 100, 160)), 0);
    }

    void chromaKeyReplacesGreenScreen()
    {
        QImage frame(160, 120, QImage::Format_RGB32);
        frame.fill(QColor(20, 180, 60)); // green screen
        QPainter(&frame).fillRect(QRect(60, 40, 40, 40), QColor(200, 60, 40)); // felt puppet
        QImage sky(320, 200, QImage::Format_RGB32);
        sky.fill(QColor(90, 150, 230));

        const QImage out = ImageTools::chromaKey(frame, {}, sky);
        QCOMPARE(out.size(), frame.size());
        QVERIFY(maxDiff(out, sky.copy(0, 0, 160, 120), QRect(0, 0, 30, 30)) <= 2);
        const QRgb puppet = out.pixel(80, 60);
        QVERIFY(qRed(puppet) > 180 && qGreen(puppet) < 80);

        const QImage cut = ImageTools::chromaKey(frame, {}, QImage());
        QVERIFY(cut.hasAlphaChannel());
        QCOMPARE(qAlpha(cut.pixel(5, 5)), 0);
        QCOMPARE(qAlpha(cut.pixel(80, 60)), 255);
    }

    void spillSuppression()
    {
        QImage frame(10, 10, QImage::Format_RGB32);
        frame.fill(QColor(150, 190, 120)); // puppet edge lit by green bounce
        ImageTools::ChromaOptions o;
        o.tolerance = 0.0; o.softness = 0.01; // keep the pixel, only fix spill
        const QRgb p = ImageTools::chromaKey(frame, o, QImage()).pixel(5, 5);
        QVERIFY(qGreen(p) <= qMax(qRed(p), qBlue(p)));
    }

    void batchKeepsOriginalsAndRestores()
    {
        ProjectManager pm;
        QVERIFY(pm.newProject(QStringLiteral("Ferramentas")));
        QImage green(80, 60, QImage::Format_RGB32);
        green.fill(QColor(20, 180, 60));
        for (int i = 0; i < 3; ++i)
            QVERIFY(pm.addFrame(green));
        const QString sky = m_home.path() + QStringLiteral("/ceu.png");
        QImage skyImg(80, 60, QImage::Format_RGB32);
        skyImg.fill(QColor(90, 150, 230));
        QVERIFY(skyImg.save(sky));

        FrameTools tools(&pm);
        QSignalSpy done(&tools, &FrameTools::finished);
        QVERIFY(tools.applyChroma({0, 2}, QColor(20, 180, 60), 0.18, 0.1, true, QUrl::fromLocalFile(sky)));
        QVERIFY(done.wait(20000));
        QVERIFY(done.first().at(0).toBool());

        QCOMPARE(QImage(pm.frameFile(0)).pixel(10, 10), qRgb(90, 150, 230));
        QCOMPARE(QImage(pm.frameFile(1)).pixel(10, 10), qRgb(20, 180, 60)); // not selected
        QVERIFY(pm.hasOriginal(0) && !pm.hasOriginal(1) && pm.hasOriginal(2));
        QVERIFY(pm.frameUrl(0).query().startsWith(QStringLiteral("v=")));

        QCOMPARE(tools.restore({0, 2}), 2);
        QCOMPARE(QImage(pm.frameFile(0)).pixel(10, 10), qRgb(20, 180, 60));
        QVERIFY(!pm.hasOriginal(0));
    }

    void cleanPlateFromFrame()
    {
        ProjectManager pm;
        QVERIFY(pm.newProject(QStringLiteral("Placa")));
        QVERIFY(pm.addFrame(gradient(64, 48)));
        QVERIFY(pm.cleanPlateUrl().isEmpty());
        QVERIFY(pm.setCleanPlateFromFrame(0));
        QVERIFY(QFile::exists(pm.cleanPlateFile()));
        QVERIFY(!pm.cleanPlateUrl().isEmpty());
        // Routing the next camera shot to the plate does not add a frame.
        pm.captureCleanPlateNext();
        QVERIFY(pm.capturingCleanPlate());
    }

    // Needs the local AI environment: IA_SMS_PYTHON (python with onnxruntime,
    // numpy, pillow), IA_SMS_AI_SCRIPT (system/ia-sms-ia.py) and
    // IA_SMS_AI_MODELS (a folder with u2netp.onnx / isnet-general-use.onnx and
    // optionally lama_fp32.onnx).
    void aiBackgroundAndFill()
    {
        if (FrameTools::segmentationModel().isEmpty())
            QSKIP("local AI not configured (see comment)");
        ProjectManager pm;
        QVERIFY(pm.newProject(QStringLiteral("IA")));
        // Puppet (red body, skin head) on a plain green set.
        QImage frame(640, 360, QImage::Format_RGB32);
        frame.fill(QColor(24, 176, 64));
        {
            QPainter p(&frame);
            p.fillRect(QRect(270, 130, 100, 140), QColor(192, 57, 43));
            p.fillRect(QRect(285, 60, 70, 70), QColor(242, 201, 160));
            p.fillRect(QRect(316, 270, 6, 80), QColor(40, 40, 40)); // support rod
        }
        QVERIFY(pm.addFrame(frame));
        QVERIFY(pm.addFrame(frame));
        const QString sky = m_home.path() + QStringLiteral("/ceu_ia.png");
        QImage skyImg(800, 450, QImage::Format_RGB32);
        skyImg.fill(QColor(90, 150, 230));
        QVERIFY(skyImg.save(sky));

        FrameTools tools(&pm);
        QSignalSpy done(&tools, &FrameTools::finished);
        QVERIFY(tools.previewAiBackground(0, QUrl::fromLocalFile(sky)));
        QVERIFY(done.wait(120000));
        QVERIFY2(done.last().at(0).toBool(), qPrintable(tools.status()));
        QVERIFY(!tools.previewUrl().isEmpty());

        QVERIFY(tools.applyAiBackground({0}, QUrl::fromLocalFile(sky)));
        QVERIFY(done.wait(120000));
        QVERIFY2(done.last().at(0).toBool(), qPrintable(tools.status()));
        const QImage out(pm.frameFile(0));
        const QRgb corner = out.pixel(20, 20), body = out.pixel(320, 200);
        QVERIFY2(qBlue(corner) > 180 && qGreen(corner) < 190, qPrintable(QColor(corner).name()));
        QVERIFY2(qRed(body) > 150 && qGreen(body) < 100, qPrintable(QColor(body).name()));
        QVERIFY(pm.hasOriginal(0));
        QCOMPARE(QImage(pm.frameFile(1)).pixel(20, 20), frame.pixel(20, 20)); // untouched

        if (FrameTools::inpaintModel().isEmpty())
            return;
        const QString mask = m_home.path() + QStringLiteral("/mascara_ia.png");
        QVERIFY(bandMask(640, 360, 310, 328).save(mask));
        QVERIFY(tools.applyAiFill({1}, mask));
        QVERIFY(done.wait(120000));
        QVERIFY2(done.last().at(0).toBool(), qPrintable(tools.status()));
        const QImage filled(pm.frameFile(1));
        QVERIFY(QColor(filled.pixel(319, 320)) != QColor(40, 40, 40)); // rod gone
        QCOMPARE(filled.pixel(100, 300), frame.pixel(100, 300));      // far pixels untouched
    }

    void upscaleWithRealEsrgan()
    {
        if (FrameTools::upscalerPath().isEmpty())
            QSKIP("set IA_SMS_REALESRGAN to the realesrgan-ncnn-vulkan binary to run");
        ProjectManager pm;
        QVERIFY(pm.newProject(QStringLiteral("Upscale")));
        QVERIFY(pm.addFrame(gradient(64, 48)));
        FrameTools tools(&pm);
        QSignalSpy done(&tools, &FrameTools::finished);
        QVERIFY(tools.upscale({0}, 2));
        QVERIFY(done.wait(300000));
        QVERIFY2(done.first().at(0).toBool(), qPrintable(tools.status()));
        QCOMPARE(QImage(pm.frameFile(0)).size(), QSize(128, 96));
        QCOMPARE(QImage(pm.originalFile(0)).size(), QSize(64, 48));
    }
};

QTEST_MAIN(TestImageTools)
#include "tst_imagetools.moc"
