#pragma once

#include <QDateTime>
#include <QFileInfo>
#include <QSize>
#include <QString>
#include <QStringList>

// Output formats shared by the quick export and the timeline.
namespace Formats {

inline QStringList ids()
{
    return {QStringLiteral("youtube"), QStringLiteral("vertical"), QStringLiteral("quadrado"), QStringLiteral("4k")};
}

inline QSize size(const QString &id)
{
    if (id == QLatin1String("vertical"))
        return {1080, 1920};
    if (id == QLatin1String("quadrado"))
        return {1080, 1080};
    if (id == QLatin1String("4k"))
        return {3840, 2160};
    return {1920, 1080};
}

// "<dir>/<base>_<timestamp>.mp4", never overwriting an earlier export made
// within the same second.
inline QString uniqueOutput(const QString &dir, const QString &base)
{
    const QString stamp = QDateTime::currentDateTime().toString(QStringLiteral("yyyyMMdd-HHmmss"));
    QString path = QStringLiteral("%1/%2_%3.mp4").arg(dir, base, stamp);
    for (int i = 2; QFileInfo::exists(path); ++i)
        path = QStringLiteral("%1/%2_%3-%4.mp4").arg(dir, base, stamp).arg(i);
    return path;
}

} // namespace Formats
