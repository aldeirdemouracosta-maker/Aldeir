#include <QImage>
#include <QSignalSpy>
#include <QTemporaryDir>
#include <QTest>

#include "dslrcamera.h"
#include "projectmanager.h"

class TestDslr : public QObject
{
    Q_OBJECT

private:
    QTemporaryDir m_home;

private slots:
    void initTestCase()
    {
        QVERIFY(m_home.isValid());
        qputenv("IA_SMS_HOME", m_home.path().toUtf8());
        qputenv("IA_SMS_GPHOTO2", QByteArray(MOCK_GPHOTO2));
        QImage img(640, 426, QImage::Format_RGB32);
        img.fill(QColor(200, 120, 60));
        const QString jpeg = m_home.path() + QStringLiteral("/dslr.jpg");
        QVERIFY(img.save(jpeg, "JPG"));
        qputenv("MOCK_GPHOTO2_JPEG", jpeg.toUtf8());
    }

    void detectLiveViewAndCapture()
    {
        DslrCamera cam;
        QVERIFY(cam.available());

        QSignalSpy cams(&cam, &DslrCamera::camerasChanged);
        cam.detect();
        QVERIFY(cams.wait(5000));
        QCOMPARE(cam.cameras().size(), 1);
        const QVariantMap c = cam.cameras().first().toMap();
        QCOMPARE(c.value(QStringLiteral("model")).toString(), QStringLiteral("Canon EOS 1100D"));
        QCOMPARE(c.value(QStringLiteral("port")).toString(), QStringLiteral("usb:001,004"));

        cam.startLiveView(c.value(QStringLiteral("port")).toString());
        QTRY_VERIFY_WITH_TIMEOUT(cam.frameCounter() >= 2, 5000);
        QCOMPARE(cam.latestFrame().size(), QSize(640, 426));

        // Capturing pauses live view, downloads the photo and resumes.
        ProjectManager pm;
        QVERIFY(pm.newProject(QStringLiteral("DSLR")));
        connect(&cam, &DslrCamera::captured, &pm, &ProjectManager::ingestCapture);
        QSignalSpy shot(&cam, &DslrCamera::captured);
        QVERIFY(cam.capture(c.value(QStringLiteral("port")).toString()));
        QVERIFY(shot.wait(10000));
        QCOMPARE(pm.frameCount(), 1);
        QCOMPARE(QImage(pm.frameFile(0)).size(), QSize(640, 426));
        QTRY_VERIFY_WITH_TIMEOUT(cam.liveView(), 5000);

        // The next shot can become the clean plate instead of a frame.
        pm.captureCleanPlateNext();
        QVERIFY(cam.capture(QString()));
        QVERIFY(shot.wait(10000));
        QCOMPARE(pm.frameCount(), 1);
        QVERIFY(QFile::exists(pm.cleanPlateFile()));
        cam.stopLiveView();
    }
};

QTEST_MAIN(TestDslr)
#include "tst_dslr.moc"
