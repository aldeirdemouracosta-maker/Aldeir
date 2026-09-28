#include <QImage>
#include <QRegularExpression>
#include <QProcess>
#include <QSignalSpy>
#include <QStandardPaths>
#include <QTemporaryDir>
#include <QTest>

#include <cmath>

#include "audiotrack.h"
#include "exporter.h"
#include "projectmanager.h"
#include "timeline.h"
#include "timelinerenderer.h"

class TestAudio : public QObject
{
    Q_OBJECT

private:
    QTemporaryDir m_home;

    QString makeAudio(const QString &name, const QString &lavfi)
    {
        const QString file = m_home.path() + QLatin1Char('/') + name;
        const int rc = QProcess::execute(QStringLiteral("ffmpeg"), {QStringLiteral("-v"), QStringLiteral("error"), QStringLiteral("-y"),
                                                                    QStringLiteral("-f"), QStringLiteral("lavfi"), QStringLiteral("-i"), lavfi, file});
        return rc == 0 ? file : QString();
    }

    static QImage gray(int level)
    {
        QImage img(160, 120, QImage::Format_RGB32);
        img.fill(QColor(level, level, level));
        return img;
    }

    static QString probe(const QString &file, const QString &entries)
    {
        QProcess p;
        p.start(QStringLiteral("ffprobe"), {QStringLiteral("-v"), QStringLiteral("error"), QStringLiteral("-show_entries"), entries,
                                            QStringLiteral("-of"), QStringLiteral("csv=p=0"), file});
        p.waitForFinished(30000);
        return QString::fromUtf8(p.readAll()).trimmed();
    }

    // Mean brightness of every decoded frame of a video.
    static QList<double> frameBrightness(const QString &video)
    {
        QProcess p;
        p.start(QStringLiteral("ffmpeg"), {QStringLiteral("-v"), QStringLiteral("error"), QStringLiteral("-i"), video,
                                           QStringLiteral("-vf"), QStringLiteral("scale=8:8,format=gray"),
                                           QStringLiteral("-f"), QStringLiteral("rawvideo"), QStringLiteral("-")});
        p.waitForFinished(60000);
        const QByteArray raw = p.readAllStandardOutput();
        QList<double> means;
        for (qsizetype i = 0; i + 64 <= raw.size(); i += 64) {
            double sum = 0;
            for (int k = 0; k < 64; ++k)
                sum += quint8(raw.at(i + k));
            means.append(sum / 64);
        }
        return means;
    }

    static double stddev(const QList<double> &v)
    {
        double mean = 0, acc = 0;
        for (double x : v) mean += x;
        mean /= qMax<qsizetype>(1, v.size());
        for (double x : v) acc += (x - mean) * (x - mean);
        return std::sqrt(acc / qMax<qsizetype>(1, v.size()));
    }

    QString exportNow(ProjectManager &pm)
    {
        Exporter exporter(&pm);
        QSignalSpy done(&exporter, &Exporter::finished);
        if (!exporter.exportVideo(QStringLiteral("quadrado"), false) || !done.wait(60000) || !done.first().at(0).toBool())
            return {};
        return done.first().at(1).toString();
    }

private slots:
    void initTestCase()
    {
        QVERIFY(m_home.isValid());
        qputenv("IA_SMS_HOME", m_home.path().toUtf8());
        if (QStandardPaths::findExecutable(QStringLiteral("ffmpeg")).isEmpty())
            QSKIP("ffmpeg not installed");
    }

    void waveformPerFrame()
    {
        ProjectManager pm;
        QVERIFY(pm.newProject(QStringLiteral("Onda")));
        pm.setFps(12);
        AudioTrack track(&pm);
        // 1 s of tone followed by 1 s of silence.
        const QString wav = makeAudio(QStringLiteral("tom_silencio.wav"), QStringLiteral("sine=f=300:d=1,apad=pad_dur=1"));
        QVERIFY(!wav.isEmpty());

        QSignalSpy spy(&track, &AudioTrack::waveformChanged);
        QVERIFY(pm.setAudio(QUrl::fromLocalFile(wav)));
        QVERIFY(QFile::exists(pm.projectPath() + QStringLiteral("/audio/tom_silencio.wav")));
        QTRY_VERIFY_WITH_TIMEOUT(track.lengthFrames() == 24 && !track.busy(), 10000);
        QVERIFY(track.waveform().at(5).toDouble() > 0.8);
        QVERIFY(track.waveform().at(20).toDouble() < 0.05);

        pm.setAudioOffset(6); // audio starts half a second into the animation
        QTRY_VERIFY_WITH_TIMEOUT(track.lengthFrames() == 30 && !track.busy(), 10000);
        QCOMPARE(track.waveform().at(3).toDouble(), 0.0);
        QVERIFY(track.waveform().at(10).toDouble() > 0.8);

        ProjectManager reopened;
        QVERIFY(reopened.openProject(pm.projectPath()));
        QCOMPARE(reopened.audioOffset(), 6);
        QCOMPARE(reopened.audioName(), QStringLiteral("tom_silencio.wav"));
    }

    void exportIncludesAudio()
    {
        ProjectManager pm;
        QVERIFY(pm.newProject(QStringLiteral("Com Som")));
        pm.setFps(12);
        for (int i = 0; i < 12; ++i)
            QVERIFY(pm.addFrame(gray(120)));
        pm.setHold(11, 6); // 17 frames ≈ 1.417 s
        // Audio longer than the animation must be cut to its length.
        QVERIFY(pm.setAudio(QUrl::fromLocalFile(makeAudio(QStringLiteral("longo.wav"), QStringLiteral("sine=f=440:d=4")))));

        const QString out = exportNow(pm);
        QVERIFY(!out.isEmpty());
        const QString streams = probe(out, QStringLiteral("stream=codec_type"));
        QVERIFY2(streams.contains(QStringLiteral("audio")), qPrintable(streams));
        const double duration = probe(out, QStringLiteral("format=duration")).toDouble();
        QVERIFY2(std::abs(duration - 17.0 / 12.0) < 0.12, qPrintable(QString::number(duration)));
    }

    void deflickerEvensOutExposure()
    {
        ProjectManager pm;
        QVERIFY(pm.newProject(QStringLiteral("Flicker")));
        pm.setFps(12);
        for (int i = 0; i < 24; ++i)
            QVERIFY(pm.addFrame(gray(i % 2 ? 150 : 100))); // lamp flickering between shots

        const QString plain = exportNow(pm);
        pm.setDeflicker(true);
        const QString smooth = exportNow(pm);
        QVERIFY(!plain.isEmpty() && !smooth.isEmpty());

        const double before = stddev(frameBrightness(plain));
        const double after = stddev(frameBrightness(smooth));
        QVERIFY2(before > 15, qPrintable(QString::number(before)));
        QVERIFY2(after < before / 2, qPrintable(QStringLiteral("%1 -> %2").arg(before).arg(after)));
    }

    void timelineCarriesSceneAudio()
    {
        if (QStandardPaths::findExecutable(QStringLiteral("melt")).isEmpty())
            QSKIP("melt not installed");
        ProjectManager pm;
        QVERIFY(pm.newProject(QStringLiteral("Dialogo")));
        pm.setFps(12);
        for (int i = 0; i < 12; ++i)
            QVERIFY(pm.addFrame(gray(90)));
        QVERIFY(pm.setAudio(QUrl::fromLocalFile(makeAudio(QStringLiteral("fala.wav"), QStringLiteral("sine=f=220:d=1")))));
        const QString scene = pm.projectPath();
        pm.newProject(QStringLiteral("Filme Dialogo"));

        Timeline tl(&pm);
        QVERIFY(tl.addScene(scene));
        TimelineRenderer renderer(&tl);
        QSignalSpy done(&renderer, &TimelineRenderer::finished);
        QVERIFY(renderer.render(false));
        QVERIFY(done.wait(120000));
        QVERIFY2(done.first().at(0).toBool(), qPrintable(renderer.status()));
        const QString out = done.first().at(1).toString();
        // Audible (not silent) audio in the film.
        QProcess p;
        p.start(QStringLiteral("ffmpeg"), {QStringLiteral("-v"), QStringLiteral("info"), QStringLiteral("-i"), out,
                                           QStringLiteral("-af"), QStringLiteral("volumedetect"), QStringLiteral("-f"),
                                           QStringLiteral("null"), QStringLiteral("-")});
        QVERIFY(p.waitForFinished(60000));
        const QString log = QString::fromUtf8(p.readAllStandardError());
        const QRegularExpressionMatch m = QRegularExpression(QStringLiteral("max_volume: (-?[0-9.]+) dB")).match(log);
        QVERIFY2(m.hasMatch(), qPrintable(log.right(300)));
        QVERIFY2(m.captured(1).toDouble() > -20.0, qPrintable(m.captured(1)));
    }

    void lipSyncWithRhubarb()
    {
        const QString speech = qEnvironmentVariable("IA_SMS_TEST_SPEECH");
        if (AudioTrack::rhubarbPath().isEmpty() || speech.isEmpty())
            QSKIP("set IA_SMS_RHUBARB and IA_SMS_TEST_SPEECH (a WAV with speech) to run");
        ProjectManager pm;
        QVERIFY(pm.newProject(QStringLiteral("Labial")));
        pm.setFps(24);
        AudioTrack track(&pm);
        QVERIFY(pm.setAudio(QUrl::fromLocalFile(speech)));
        QTRY_VERIFY_WITH_TIMEOUT(track.lengthFrames() > 0 && !track.busy(), 10000);
        QSignalSpy mouths(&track, &AudioTrack::mouthsChanged);
        QVERIFY(track.runLipSync());
        QTRY_VERIFY_WITH_TIMEOUT(!track.busy() && !track.mouths().isEmpty(), 180000);
        QSet<QString> shapes;
        for (const QVariant &m : track.mouths())
            shapes.insert(m.toString());
        QVERIFY2(shapes.size() >= 4, qPrintable(QStringList(shapes.values()).join(',')));
        QCOMPARE(track.mouths().size(), track.lengthFrames());
    }
};

QTEST_MAIN(TestAudio)
#include "tst_audio.moc"
