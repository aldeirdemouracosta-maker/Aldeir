#include <QImage>
#include <QJsonDocument>
#include <QJsonObject>
#include <QSignalSpy>
#include <QTemporaryDir>
#include <QTest>

#include "scenery.h"

class TestScenery : public QObject
{
    Q_OBJECT

private:
    QTemporaryDir m_home;

private slots:
    void initTestCase()
    {
        QVERIFY(m_home.isValid());
        qputenv("IA_SMS_HOME", m_home.path().toUtf8());
        qputenv("IA_SMS_SD", QByteArray(MOCK_SD));
        const QString model = m_home.path() + QStringLiteral("/sd15.safetensors");
        QFile(model).open(QIODevice::WriteOnly);
        qputenv("IA_SMS_SD_MODEL", model.toUtf8());
    }

    void promptsAndSizes()
    {
        QCOMPARE(SceneryStudio::sizeFor(QStringLiteral("16:9")), QSize(768, 432));
        QCOMPARE(SceneryStudio::sizeFor(QStringLiteral("9:16")), QSize(432, 768));
        QVERIFY(SceneryStudio::stylePrompt(QStringLiteral("feltro"), QStringLiteral("cozy kitchen")).startsWith(QStringLiteral("cozy kitchen, ")));
        QVERIFY(SceneryStudio::stylePrompt(QStringLiteral("feltro"), QStringLiteral("x")).contains(QStringLiteral("felt")));
    }

    void generateImportRemove()
    {
        SceneryStudio studio;
        QVERIFY(studio.generatorAvailable());
        QSignalSpy done(&studio, &SceneryStudio::generated);
        QSignalSpy progress(&studio, &SceneryStudio::progressChanged);
        QVERIFY(studio.generate(QStringLiteral("a tiny cozy kitchen"), QStringLiteral("massinha"), QStringLiteral("16:9"), 6, 1234));
        QVERIFY(done.wait(30000));
        const QString file = done.first().at(0).toUrl().toLocalFile();
        QCOMPARE(QImage(file).size(), QSize(768, 432));
        QVERIFY(progress.count() >= 6);
        QFile meta(file + QStringLiteral(".json"));
        QVERIFY(meta.open(QIODevice::ReadOnly));
        const QJsonObject obj = QJsonDocument::fromJson(meta.readAll()).object();
        QCOMPARE(obj.value(QStringLiteral("seed")).toInt(), 1234);
        QVERIFY(obj.value(QStringLiteral("fullPrompt")).toString().contains(QStringLiteral("claymation")));

        QCOMPARE(studio.items().size(), 1);
        QVERIFY(studio.items().first().toMap().value(QStringLiteral("generated")).toBool());

        QImage photo(100, 60, QImage::Format_RGB32);
        photo.fill(Qt::darkGreen);
        const QString src = m_home.path() + QStringLiteral("/quintal.jpg");
        QVERIFY(photo.save(src));
        QCOMPARE(studio.importImages({QUrl::fromLocalFile(src), QUrl::fromLocalFile(src)}), 2);
        QCOMPARE(studio.items().size(), 3);

        QVERIFY(studio.remove(QUrl::fromLocalFile(file)));
        QCOMPARE(studio.items().size(), 2);
        QVERIFY(!studio.remove(QUrl::fromLocalFile(src))); // outside the library
    }
};

QTEST_MAIN(TestScenery)
#include "tst_scenery.moc"
