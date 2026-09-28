#include <QFile>
#include <QSignalSpy>
#include <QTemporaryDir>
#include <QTest>

#include "systemmodes.h"

class TestModes : public QObject
{
    Q_OBJECT

private slots:
    void modeFromContext()
    {
        QCOMPARE(SystemModes::modeFor(QStringLiteral("captura"), false, false), QStringLiteral("captura"));
        QCOMPARE(SystemModes::modeFor(QStringLiteral("timeline"), false, false), QStringLiteral("edicao"));
        QCOMPARE(SystemModes::modeFor(QStringLiteral("ia"), false, false), QStringLiteral("ia"));
        QCOMPARE(SystemModes::modeFor(QStringLiteral("inicio"), false, false), QStringLiteral("normal"));
        // Background work wins over the visible page.
        QCOMPARE(SystemModes::modeFor(QStringLiteral("captura"), false, true), QStringLiteral("ia"));
        QCOMPARE(SystemModes::modeFor(QStringLiteral("ia"), true, true), QStringLiteral("render"));
    }

    void appliesThroughHelper()
    {
        QTemporaryDir dir;
        const QString log = dir.path() + QStringLiteral("/chamadas.txt");
        const QString helper = dir.path() + QStringLiteral("/ia-sms-modo");
        QFile f(helper);
        QVERIFY(f.open(QIODevice::WriteOnly));
        f.write(QStringLiteral("#!/bin/sh\necho \"$@\" >> '%1'\n").arg(log).toUtf8());
        f.close();
        f.setPermissions(f.permissions() | QFileDevice::ExeOwner);
        qputenv("IA_SMS_MODE_HELPER", helper.toUtf8());

        SystemModes modes;
        QVERIFY(modes.available());
        QSignalSpy applied(&modes, &SystemModes::applied);
        // Rapid page changes collapse into the last one (debounce).
        modes.updateContext(QStringLiteral("captura"), false, false);
        modes.updateContext(QStringLiteral("timeline"), false, false);
        QVERIFY(applied.wait(5000));
        QCOMPARE(modes.mode(), QStringLiteral("edicao"));
        QVERIFY(applied.first().at(1).toBool());

        modes.updateContext(QStringLiteral("timeline"), true, false);
        QVERIFY(applied.wait(5000));
        QCOMPARE(modes.mode(), QStringLiteral("render"));

        // Manual mode ignores the context.
        modes.setAutomatic(false);
        modes.updateContext(QStringLiteral("captura"), false, false);
        QVERIFY(!applied.wait(1500));
        QCOMPARE(modes.mode(), QStringLiteral("render"));

        QFile calls(log);
        QVERIFY(calls.open(QIODevice::ReadOnly));
        const QStringList lines = QString::fromUtf8(calls.readAll()).trimmed().split(QLatin1Char('\n'));
        QCOMPARE(lines.size(), 2);
        QVERIFY(lines.at(0).startsWith(QStringLiteral("edicao --pid ")));
        QVERIFY(lines.at(1).startsWith(QStringLiteral("render --pid ")));
    }
};

QTEST_MAIN(TestModes)
#include "tst_modes.moc"
