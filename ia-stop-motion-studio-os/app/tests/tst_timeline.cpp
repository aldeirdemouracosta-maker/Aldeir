#include <QImage>
#include <QProcess>
#include <QSignalSpy>
#include <QStandardPaths>
#include <QTemporaryDir>
#include <QTest>

#include "projectmanager.h"
#include "timeline.h"
#include "timelinerenderer.h"

class TestTimeline : public QObject
{
    Q_OBJECT

private:
    QTemporaryDir m_home;

    static QImage frame(const QColor &color)
    {
        QImage img(320, 240, QImage::Format_RGB32);
        img.fill(color);
        return img;
    }

    // Scene of `photos` photos at 12 fps (0.5 s each with hold 6).
    static QString makeScene(ProjectManager &pm, const QString &name, const QColor &color, int photos)
    {
        pm.newProject(name);
        for (int i = 0; i < photos; ++i)
            pm.addFrame(frame(color));
        return pm.projectPath();
    }

    static bool haveTools()
    {
        return !QStandardPaths::findExecutable(QStringLiteral("melt")).isEmpty()
            && !QStandardPaths::findExecutable(QStringLiteral("ffmpeg")).isEmpty()
            && !QStandardPaths::findExecutable(QStringLiteral("ffprobe")).isEmpty();
    }

    static QImage grab(const QString &video, double seconds)
    {
        const QString png = video + QStringLiteral(".%1.png").arg(seconds);
        QProcess::execute(QStringLiteral("ffmpeg"), {QStringLiteral("-loglevel"), QStringLiteral("error"), QStringLiteral("-y"),
                                                     QStringLiteral("-ss"), QString::number(seconds), QStringLiteral("-i"), video,
                                                     QStringLiteral("-frames:v"), QStringLiteral("1"), png});
        return QImage(png);
    }

private slots:
    void initTestCase()
    {
        QVERIFY(m_home.isValid());
        if (qEnvironmentVariableIsSet("KEEP_TEST_DIR")) { m_home.setAutoRemove(false); qInfo() << m_home.path(); }
        qputenv("IA_SMS_HOME", m_home.path().toUtf8());
    }

    void layoutSplitAndPersistence()
    {
        ProjectManager pm;
        const QString red = makeScene(pm, QStringLiteral("Vermelha"), Qt::red, 12);   // 1 s
        const QString blue = makeScene(pm, QStringLiteral("Azul"), Qt::blue, 24);     // 2 s
        pm.newProject(QStringLiteral("Filme"));

        Timeline tl(&pm);
        QCOMPARE(tl.fps(), 24);
        QVERIFY(tl.addScene(red));
        QVERIFY(tl.addScene(blue));
        QCOMPARE(tl.duration(), 72);

        tl.setVideoProperty(1, QStringLiteral("transition"), 12);
        QCOMPARE(tl.videoList().at(1).start, 12);
        QCOMPARE(tl.duration(), 60);
        tl.setVideoProperty(1, QStringLiteral("transition"), 500); // clamped to half the shorter clip
        QCOMPARE(tl.videoList().at(1).transition, 12);

        QVERIFY(tl.splitAt(40));
        QCOMPARE(tl.videoList().size(), 3);
        QCOMPARE(tl.duration(), 60);

        tl.addTitle(QStringLiteral("Cena 1"), 6);
        QVERIFY(QFile::exists(tl.titleList().first().image));
        QCOMPARE(QImage(tl.titleList().first().image).size(), QSize(1920, 1080));

        const QVariantList layers = tl.layersAt(18); // inside the dissolve and the title
        QCOMPARE(layers.size(), 3);
        QCOMPARE(layers.last().toMap().value(QStringLiteral("kind")).toString(), QStringLiteral("title"));

        tl.setFps(12); // positions keep their time in seconds
        QCOMPARE(tl.duration(), 39); // the 3 s title now ends the film
        QCOMPARE(tl.titleList().first().start, 3);

        Timeline reopened(&pm);
        QCOMPARE(reopened.videoList().size(), 3);
        QCOMPARE(reopened.fps(), 12);
        QCOMPARE(reopened.titleList().first().text, QStringLiteral("Cena 1"));
    }

    void undoRedoAndReorder()
    {
        ProjectManager pm;
        const QString a = makeScene(pm, QStringLiteral("UA"), Qt::red, 12);
        const QString b = makeScene(pm, QStringLiteral("UB"), Qt::blue, 24);
        const QString c = makeScene(pm, QStringLiteral("UC"), Qt::green, 6);
        pm.newProject(QStringLiteral("Filme Undo"));
        Timeline tl(&pm);
        QVERIFY(!tl.canUndo());
        tl.addScene(a);
        tl.addScene(b);
        tl.addScene(c);
        auto names = [&] {
            QStringList n;
            for (const auto &clip : tl.videoList()) n << clip.name;
            return n.join(QLatin1Char(','));
        };
        QCOMPARE(names(), QStringLiteral("UA,UB,UC"));

        tl.moveClipTo(2, 0); // drag the last clip to the front
        QCOMPARE(names(), QStringLiteral("UC,UA,UB"));
        tl.removeVideo(1);
        QCOMPARE(names(), QStringLiteral("UC,UB"));

        tl.undo();
        QCOMPARE(names(), QStringLiteral("UC,UA,UB"));
        tl.undo();
        QCOMPARE(names(), QStringLiteral("UA,UB,UC"));
        QVERIFY(tl.canRedo());
        tl.redo();
        QCOMPARE(names(), QStringLiteral("UC,UA,UB"));

        // A slider drag (many volume changes) is a single undo step.
        tl.addTitle(QStringLiteral("T"), 0);
        for (int i = 1; i <= 10; ++i)
            tl.setTitleProperty(0, QStringLiteral("size"), 8 + i);
        QCOMPARE(tl.titleList().first().size, 18);
        tl.undo();
        QCOMPARE(tl.titleList().first().size, 8);
        tl.undo();
        QVERIFY(tl.titleList().isEmpty());

        // A new edit clears redo; the state on disk follows undo.
        tl.redo();
        tl.setVideoProperty(0, QStringLiteral("length"), 4);
        QVERIFY(!tl.canRedo());
        tl.undo();
        Timeline reopened(&pm);
        QCOMPARE(reopened.videoList().first().out - reopened.videoList().first().in, 12);
    }

    void renderFilm()
    {
        if (!haveTools())
            QSKIP("melt/ffmpeg not installed");

        ProjectManager pm;
        const QString red = makeScene(pm, QStringLiteral("R"), Qt::red, 12);   // 1 s
        const QString blue = makeScene(pm, QStringLiteral("B"), Qt::blue, 24); // 2 s
        pm.newProject(QStringLiteral("Filme Render"));

        Timeline tl(&pm);
        tl.setFormat(QStringLiteral("quadrado"));
        tl.addScene(red);
        tl.addScene(blue);
        tl.setVideoProperty(1, QStringLiteral("transition"), 12); // 0.5 s dissolve
        tl.addTitle(QStringLiteral("Olá"), 0);
        tl.setTitleProperty(0, QStringLiteral("length"), 12);
        tl.setTitleProperty(0, QStringLiteral("position"), QStringLiteral("center"));

        // 3 s of generated tone as music.
        const QString tone = m_home.path() + QStringLiteral("/tom.wav");
        QCOMPARE(QProcess::execute(QStringLiteral("ffmpeg"), {QStringLiteral("-loglevel"), QStringLiteral("error"),
                                                              QStringLiteral("-y"), QStringLiteral("-f"), QStringLiteral("lavfi"),
                                                              QStringLiteral("-i"), QStringLiteral("sine=f=440:d=3"), tone}), 0);
        QCOMPARE(tl.addMedia({QUrl::fromLocalFile(tone)}), 1);
        QCOMPARE(tl.audioList().size(), 1);
        QCOMPARE(tl.duration(), 72); // audio (3 s) is longer than video (2.5 s)

        TimelineRenderer renderer(&tl);
        QSignalSpy done(&renderer, &TimelineRenderer::finished);
        QVERIFY(renderer.render(false));
        QVERIFY(done.wait(180000));
        QVERIFY2(done.first().at(0).toBool(), qPrintable(renderer.status()));
        const QString out = done.first().at(1).toString();

        QProcess probe;
        probe.start(QStringLiteral("ffprobe"), {QStringLiteral("-v"), QStringLiteral("error"),
                                                QStringLiteral("-show_entries"), QStringLiteral("stream=codec_type,width,height"),
                                                QStringLiteral("-of"), QStringLiteral("csv=p=0"), out});
        QVERIFY(probe.waitForFinished(30000));
        const QString streams = QString::fromUtf8(probe.readAll());
        QVERIFY2(streams.contains(QStringLiteral("video,1080,1080")), qPrintable(streams));
        QVERIFY2(streams.contains(QStringLiteral("audio")), qPrintable(streams));

        auto isRed = [](QRgb c) { return qRed(c) > 180 && qBlue(c) < 80; };
        auto isBlue = [](QRgb c) { return qBlue(c) > 180 && qRed(c) < 80; };
        const QImage start = grab(out, 0.2);
        const QImage mid = grab(out, 0.75);
        const QImage end = grab(out, 2.0);
        QVERIFY(!start.isNull() && !mid.isNull() && !end.isNull());
        // 4:3 scenes are letterboxed in the square frame: sample the left edge
        // at mid height for the video, and look for the white title text in
        // the centre.
        const QPoint edge(20, 540);
        QVERIFY(isRed(start.pixel(edge)));
        int brightest = 0;
        for (int y = 480; y < 600; y += 2)
            for (int x = 440; x < 640; x += 2)
                brightest = qMax(brightest, qGray(start.pixel(x, y)));
        QVERIFY2(brightest > 220, "title text not found");
        // Mid-dissolve is a mix of red and blue.
        const QRgb m = mid.pixel(edge);
        QVERIFY2(qRed(m) > 50 && qBlue(m) > 50, qPrintable(QColor(m).name()));
        QVERIFY(isBlue(end.pixel(edge)));

        QVERIFY(QFile::exists(tl.workDir() + QStringLiteral("/filme.mlt")));
    }
};

QTEST_MAIN(TestTimeline)
#include "tst_timeline.moc"
