#include <QImage>
#include <QSignalSpy>
#include <QTemporaryDir>
#include <QTest>

#include "characters.h"
#include "frametools.h"
#include "imagetools.h"
#include "projectmanager.h"

class TestCharacters : public QObject
{
    Q_OBJECT

private:
    QTemporaryDir m_home;

private slots:
    void initTestCase()
    {
        QVERIFY(m_home.isValid());
        qputenv("IA_SMS_HOME", m_home.path().toUtf8());
    }

    void defaultCharacterHasAllMouths()
    {
        CharacterLibrary lib;
        QVERIFY(lib.characters().isEmpty());
        lib.ensureDefault();
        QCOMPARE(lib.characters().size(), 1);
        const QVariantMap c = lib.characters().first().toMap();
        QCOMPARE(c.value(QStringLiteral("mouthCount")).toInt(), 9);
        // Distinct drawings: open "D" has far more ink than closed "A".
        auto ink = [](const QImage &img) {
            int n = 0;
            for (int y = 0; y < img.height(); ++y)
                for (int x = 0; x < img.width(); ++x)
                    n += qAlpha(img.pixel(x, y)) > 0;
            return n;
        };
        QVERIFY(ink(ImageTools::defaultMouth(QStringLiteral("D"))) > 3 * ink(ImageTools::defaultMouth(QStringLiteral("A"))));
        lib.ensureDefault(); // idempotent
        QCOMPARE(lib.characters().size(), 1);
    }

    void createEditRemove()
    {
        CharacterLibrary lib;
        const QString dir = lib.createCharacter(QStringLiteral("Dona Feltro"));
        QVERIFY(!dir.isEmpty());
        QImage mouth(100, 50, QImage::Format_ARGB32);
        mouth.fill(QColor(200, 0, 0, 255));
        const QString file = m_home.path() + QStringLiteral("/boca.png");
        QVERIFY(mouth.save(file));
        QVERIFY(lib.setMouth(dir, QStringLiteral("E"), QUrl::fromLocalFile(file)));
        QVERIFY(!lib.setMouth(dir, QStringLiteral("Z"), QUrl::fromLocalFile(file)));
        QVERIFY(!lib.mouthUrl(dir, QStringLiteral("E")).isEmpty());
        QVERIFY(lib.mouthUrl(dir, QStringLiteral("A")).isEmpty());
        QVERIFY(lib.renameCharacter(dir, QStringLiteral("Dona Feltro 2")));
        QCOMPARE(lib.characterName(dir), QStringLiteral("Dona Feltro 2"));
        const int before = lib.characters().size();
        QVERIFY(lib.removeCharacter(dir));
        QCOMPARE(lib.characters().size(), before - 1);
    }

    void overlayPlacesMouth()
    {
        QImage frame(400, 200, QImage::Format_RGB32);
        frame.fill(Qt::white);
        QImage mouth(40, 20, QImage::Format_ARGB32);
        mouth.fill(Qt::transparent);
        for (int y = 5; y < 15; ++y)
            for (int x = 10; x < 30; ++x)
                mouth.setPixel(x, y, qRgba(0, 0, 255, 255));
        // 25% of 400 px = 100 px wide (2.5× scale), centred at (200, 100).
        const QImage out = ImageTools::overlay(frame, mouth, QPointF(0.5, 0.5), 0.25);
        QCOMPARE(out.pixel(200, 100), qRgb(0, 0, 255));
        QCOMPARE(out.pixel(160, 100), qRgb(255, 255, 255)); // transparent part of the mouth
        QCOMPARE(out.pixel(10, 10), qRgb(255, 255, 255));
    }

    void applyMouthsPerFrame()
    {
        CharacterLibrary lib;
        const QString dir = lib.createCharacter(QStringLiteral("Teste"));
        QImage red(20, 10, QImage::Format_ARGB32), green(20, 10, QImage::Format_ARGB32);
        red.fill(Qt::red);
        green.fill(Qt::green);
        red.save(m_home.path() + QStringLiteral("/r.png"));
        green.save(m_home.path() + QStringLiteral("/g.png"));
        QVERIFY(lib.setMouth(dir, QStringLiteral("A"), QUrl::fromLocalFile(m_home.path() + QStringLiteral("/r.png"))));
        QVERIFY(lib.setMouth(dir, QStringLiteral("D"), QUrl::fromLocalFile(m_home.path() + QStringLiteral("/g.png"))));

        ProjectManager pm;
        QVERIFY(pm.newProject(QStringLiteral("Bocas")));
        QImage blank(200, 100, QImage::Format_RGB32);
        blank.fill(Qt::white);
        for (int i = 0; i < 3; ++i)
            QVERIFY(pm.addFrame(blank));
        pm.setCharacterPath(dir);
        pm.setMouthCenter(QPointF(0.5, 0.5));
        pm.setMouthWidth(0.2);

        FrameTools tools(&pm);
        QSignalSpy done(&tools, &FrameTools::finished);
        const QVariantMap shapes{{QStringLiteral("0"), QStringLiteral("A")}, {QStringLiteral("1"), QStringLiteral("D")},
                                 {QStringLiteral("2"), QStringLiteral("")}};
        QVERIFY(tools.applyMouths({0, 1, 2}, shapes, dir, 0.5, 0.5, 0.2));
        QVERIFY(done.wait(10000));
        QCOMPARE(QImage(pm.frameFile(0)).pixel(100, 50), qRgb(255, 0, 0));
        QCOMPARE(QImage(pm.frameFile(1)).pixel(100, 50), qRgb(0, 255, 0));
        QCOMPARE(QImage(pm.frameFile(2)).pixel(100, 50), qRgb(255, 255, 255)); // no shape → untouched
        QVERIFY(!pm.hasOriginal(2));

        ProjectManager reopened;
        QVERIFY(reopened.openProject(pm.projectPath()));
        QCOMPARE(reopened.characterPath(), dir);
        QCOMPARE(reopened.mouthWidth(), 0.2);
    }
};

QTEST_MAIN(TestCharacters)
#include "tst_characters.moc"
