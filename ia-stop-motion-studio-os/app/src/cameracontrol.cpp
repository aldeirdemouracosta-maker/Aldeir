#include "cameracontrol.h"

#include <QProcess>
#include <QStandardPaths>
#include <QStringList>

bool CameraControl::available() const
{
    return !QStandardPaths::findExecutable(QStringLiteral("v4l2-ctl")).isEmpty();
}

QString CameraControl::setManual(const QCameraDevice &device, bool manual)
{
    const QString node = QString::fromUtf8(device.id());
    if (!available() || !node.startsWith(QLatin1String("/dev/video")))
        return {};

    struct Control {
        QString label;
        QStringList names; // newer kernels first, then legacy names
        int manualValue;
        int autoValue;
    };
    const QList<Control> controls{
        {tr("exposição"), {QStringLiteral("auto_exposure"), QStringLiteral("exposure_auto")}, 1, 3},
        {tr("balanço de branco"), {QStringLiteral("white_balance_automatic"), QStringLiteral("white_balance_temperature_auto")}, 0, 1},
        {tr("foco"), {QStringLiteral("focus_automatic_continuous"), QStringLiteral("focus_auto")}, 0, 1},
    };

    QStringList changed;
    for (const Control &c : controls) {
        for (const QString &name : c.names) {
            QProcess p;
            p.start(QStringLiteral("v4l2-ctl"),
                    {QStringLiteral("-d"), node,
                     QStringLiteral("--set-ctrl=%1=%2").arg(name).arg(manual ? c.manualValue : c.autoValue)});
            if (p.waitForFinished(2000) && p.exitStatus() == QProcess::NormalExit && p.exitCode() == 0) {
                changed << c.label;
                break;
            }
        }
    }
    return changed.isEmpty() ? QString() : QStringLiteral("V4L2 (%1)").arg(changed.join(QStringLiteral(", ")));
}
