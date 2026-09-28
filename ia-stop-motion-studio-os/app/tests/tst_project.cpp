#include <QImage>
#include <QJsonDocument>
#include <QJsonObject>
#include <QProcess>
#include <QSignalSpy>
#include <QStandardPaths>
#include <QTemporaryDir>
#include <QTest>

#include "exporter.h"
#include "projectmanager.h"

class TestProject : public QObject
{
    Q_OBJECT

private:
    QTemporaryDir m_home;

    static QImage frame(int i)
    {
        QImage img(320, 240, QImage::Format_RGB32);
        img.fill(QColor::fromHsv((i * 40) % 360, 200, 220));
        return img;
    }

private slots:
    void initTestCase()
    {
        QVERIFY(m_home.isValid());
        qputenv("IA_SMS_HOME", m_home.path().toUtf8());
    }

    void captureHoldDeleteAndReopen()
    {
        ProjectManager pm;
        QVERIFY(pm.newProject(QStringLiteral("Teste/Bonecos")));
        QCOMPARE(pm.projectName(), QStringLiteral("Teste-Bonecos"));

        for (int i = 0; i < 5; ++i)
            QVERIFY(pm.addFrame(frame(i)));
        QCOMPARE(pm.frameCount(), 5);

        pm.setHold(1, 3);
        QCOMPARE(pm.totalFrames(), 7);
        pm.setHold(1, 100); // clamped
        QCOMPARE(pm.holdAt(1), 24);
        pm.setHold(1, 3);

        const QString last = pm.frameFile(4);
        QVERIFY(pm.deleteLastFrame());
        QCOMPARE(pm.frameCount(), 4);
        QVERIFY(!QFile::exists(last));
        QVERIFY(QFile::exists(pm.projectPath() + QStringLiteral("/lixeira/frame_000005.png")));

        // New frames never reuse a deleted frame's file name.
        QVERIFY(pm.addFrame(frame(9)));
        QVERIFY(pm.frameFile(4).endsWith(QStringLiteral("frame_000006.png")));

        ProjectManager reopened;
        QVERIFY(reopened.openProject(pm.projectPath()));
        QCOMPARE(reopened.frameCount(), 5);
        QCOMPARE(reopened.holdAt(1), 3);
        QCOMPARE(reopened.resolutionText(), QStringLiteral("240p"));
    }

    void manifestIsValidJson()
    {
        ProjectManager pm;
        QVERIFY(pm.newProject(QStringLiteral("Json")));
        QVERIFY(pm.addFrame(frame(1)));
        pm.setFps(24);
        QFile f(pm.projectPath() + QStringLiteral("/project.json"));
        QVERIFY(f.open(QIODevice::ReadOnly));
        const QJsonObject obj = QJsonDocument::fromJson(f.readAll()).object();
        QCOMPARE(obj.value(QStringLiteral("fps")).toInt(), 24);
        QCOMPARE(obj.value(QStringLiteral("frames")).toArray().size(), 1);
    }

    void exportRespectsHolds()
    {
        if (QStandardPaths::findExecutable(QStringLiteral("ffmpeg")).isEmpty()
            || QStandardPaths::findExecutable(QStringLiteral("ffprobe")).isEmpty())
            QSKIP("ffmpeg/ffprobe not installed");

        ProjectManager pm;
        QVERIFY(pm.newProject(QStringLiteral("Export")));
        for (int i = 0; i < 6; ++i)
            QVERIFY(pm.addFrame(frame(i)));
        pm.setHold(2, 4); // 6 photos, holds 1,1,4,1,1,2 -> 10 video frames
        pm.setHold(5, 2); // a hold on the last photo must survive the concat trick
        pm.setFps(12);

        Exporter exporter(&pm);
        QSignalSpy done(&exporter, &Exporter::finished);
        QVERIFY(exporter.exportVideo(QStringLiteral("quadrado"), false));
        QVERIFY(done.wait(60000));
        QVERIFY(done.first().at(0).toBool());
        const QString out = done.first().at(1).toString();
        QVERIFY(QFile::exists(out));

        QProcess probe;
        probe.start(QStringLiteral("ffprobe"),
                    {QStringLiteral("-v"), QStringLiteral("error"), QStringLiteral("-count_frames"),
                     QStringLiteral("-select_streams"), QStringLiteral("v:0"),
                     QStringLiteral("-show_entries"), QStringLiteral("stream=nb_read_frames,width,height"),
                     QStringLiteral("-of"), QStringLiteral("csv=p=0"), out});
        QVERIFY(probe.waitForFinished(30000));
        const QStringList fields = QString::fromUtf8(probe.readAll()).trimmed().split(QLatin1Char(','));
        QCOMPARE(fields.value(0), QStringLiteral("1080"));
        QCOMPARE(fields.value(1), QStringLiteral("1080"));
        QCOMPARE(fields.value(2), QStringLiteral("10"));
    }
};

QTEST_MAIN(TestProject)
#include "tst_project.moc"
