#include <QImage>
#include <QSignalSpy>
#include <QTemporaryDir>
#include <QTest>

#include "projectmanager.h"
#include "speechtools.h"
#include "timeline.h"

class TestSpeech : public QObject
{
    Q_OBJECT

private:
    QTemporaryDir m_home;

    QString tone(const QString &name, double seconds)
    {
        const QString f = m_home.path() + QLatin1Char('/') + name;
        QProcess::execute(QStringLiteral("ffmpeg"), {QStringLiteral("-v"), QStringLiteral("error"), QStringLiteral("-y"),
                                                     QStringLiteral("-f"), QStringLiteral("lavfi"), QStringLiteral("-i"),
                                                     QStringLiteral("sine=f=300:d=%1").arg(seconds), f});
        return f;
    }

private slots:
    void initTestCase()
    {
        QVERIFY(m_home.isValid());
        qputenv("IA_SMS_HOME", m_home.path().toUtf8());
        qputenv("IA_SMS_WHISPER", QByteArray(MOCK_WHISPER));
        const QString model = m_home.path() + QStringLiteral("/ggml-base.bin");
        QFile(model).open(QIODevice::WriteOnly);
        qputenv("IA_SMS_WHISPER_MODEL", model.toUtf8());
        qputenv("IA_SMS_PIPER", QByteArray(MOCK_PIPER));
        const QString voice = m_home.path() + QStringLiteral("/pt_BR-teste.onnx");
        QFile(voice).open(QIODevice::WriteOnly);
        qputenv("IA_SMS_PIPER_VOICE", voice.toUtf8());
    }

    void parsesSrt()
    {
        const QVariantList s = SpeechTools::parseSrt(QStringLiteral(
            "1\r\n00:00:01,000 --> 00:00:02,500\r\nOi\r\n\r\n2\n00:01:00.250 --> 00:01:01,000\nduas\nlinhas\n\n3\nsem tempo\n"));
        QCOMPARE(s.size(), 2);
        QCOMPARE(s.at(0).toMap().value(QStringLiteral("end")).toDouble(), 2.5);
        QCOMPARE(s.at(1).toMap().value(QStringLiteral("start")).toDouble(), 60.25);
        QCOMPARE(s.at(1).toMap().value(QStringLiteral("text")).toString(), QStringLiteral("duas\nlinhas"));
    }

    void subtitlesOnTimeline()
    {
        ProjectManager pm;
        // Scene of 4 s at 12 fps whose soundtrack starts at scene frame 12 (1 s).
        QVERIFY(pm.newProject(QStringLiteral("Cena Falada")));
        pm.setFps(12);
        QImage img(64, 48, QImage::Format_RGB32);
        img.fill(Qt::gray);
        for (int i = 0; i < 48; ++i)
            QVERIFY(pm.addFrame(img));
        QVERIFY(pm.setAudio(QUrl::fromLocalFile(tone(QStringLiteral("fala.wav"), 3))));
        pm.setAudioOffset(12);
        const QString sceneDir = pm.projectPath();
        pm.newProject(QStringLiteral("Filme Legendado"));

        Timeline tl(&pm); // 24 fps
        QVERIFY(tl.addScene(sceneDir));
        const QString music = tone(QStringLiteral("musica.wav"), 4);
        QCOMPARE(tl.addMedia({QUrl::fromLocalFile(music)}, 48), 1); // music starts at 2 s
        const QStringList sources = tl.speechSources();
        QCOMPARE(sources.size(), 2);

        SpeechTools speech;
        QVERIFY(speech.whisperAvailable());
        QSignalSpy done(&speech, &SpeechTools::transcriptionFinished);
        QVERIFY(speech.transcribe(sources));
        QVERIFY(done.wait(30000));
        const QVariantMap results = done.first().at(0).toMap();
        QCOMPARE(results.size(), 2);

        tl.addTitle(QStringLiteral("Título manual"), 0);
        QCOMPARE(tl.setSubtitles(results), 4);
        // Scene line 1: audio 0.5–1.5 s + 1 s offset → timeline 1.5–2.5 s.
        const auto titles = tl.titleList();
        auto find = [&](const QString &text, int start) {
            for (const auto &t : titles)
                if (t.kind == QLatin1String("legenda") && t.text == text && t.start == start)
                    return t.length;
            return -1;
        };
        QCOMPARE(find(QStringLiteral("Olá, eu sou o boneco!"), 36), 24);
        // Music line 1 at 2 s + 0.5 s = 2.5 s.
        QCOMPARE(find(QStringLiteral("Olá, eu sou o boneco!"), 60), 24);
        // Scene line 2 (audio 2–3.25 s → 3–4.25 s) is cut at the clip end (4 s).
        QCOMPARE(find(QStringLiteral("Vamos começar\no filme."), 72), 24);
        QCOMPARE(tl.subtitleCount(), 4);
        // Re-running replaces subtitles and keeps manual titles; cache hit.
        QSignalSpy again(&speech, &SpeechTools::transcriptionFinished);
        QVERIFY(speech.transcribe(sources));
        QVERIFY(again.count() == 1 || again.wait(5000));
        QCOMPARE(tl.setSubtitles(again.first().at(0).toMap()), 4);
        QCOMPARE(tl.titleList().size(), 5);
        tl.undo();
        QCOMPARE(tl.subtitleCount(), 4);
    }

    void narration()
    {
        SpeechTools speech;
        QVERIFY(speech.piperAvailable());
        const QString out = m_home.path() + QStringLiteral("/narracao.wav");
        QSignalSpy ready(&speech, &SpeechTools::narrationReady);
        QVERIFY(speech.narrate(QStringLiteral("Era uma vez um boneco de pano que queria voar."), out));
        QVERIFY(ready.wait(20000));
        QCOMPARE(ready.first().at(0).toString(), out);
        QVERIFY(QFileInfo(out).size() > 1000);
    }
};

QTEST_MAIN(TestSpeech)
#include "tst_speech.moc"
