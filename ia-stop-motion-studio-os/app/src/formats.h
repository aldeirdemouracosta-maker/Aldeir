#pragma once

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

} // namespace Formats
