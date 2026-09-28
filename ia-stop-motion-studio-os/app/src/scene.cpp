#include "scene.h"

#include <QFile>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QTextStream>

int Scene::totalFrames() const
{
    int total = 0;
    for (const Frame &f : frames)
        total += f.hold;
    return total;
}

int Scene::frameIndexAt(double seconds) const
{
    if (frames.isEmpty())
        return -1;
    int target = int(seconds * fps);
    for (int i = 0; i < frames.size(); ++i) {
        target -= frames.at(i).hold;
        if (target < 0)
            return i;
    }
    return frames.size() - 1;
}

Scene Scene::load(const QString &dir)
{
    Scene scene;
    scene.dir = QFileInfo(dir).absoluteFilePath();
    QFile file(scene.dir + QStringLiteral("/project.json"));
    if (!file.open(QIODevice::ReadOnly))
        return scene;
    const QJsonObject obj = QJsonDocument::fromJson(file.readAll()).object();
    scene.name = obj.value(QStringLiteral("name")).toString(QFileInfo(dir).fileName());
    scene.fps = qMax(1, obj.value(QStringLiteral("fps")).toInt(12));
    for (const QJsonValue &v : obj.value(QStringLiteral("frames")).toArray()) {
        const QJsonObject f = v.toObject();
        const QString path = scene.dir + QLatin1Char('/') + f.value(QStringLiteral("file")).toString();
        if (QFileInfo::exists(path))
            scene.frames.append({path, qMax(1, f.value(QStringLiteral("hold")).toInt(1))});
    }
    return scene;
}

bool Scene::writeConcatList(const QString &path) const
{
    QFile file(path);
    if (!file.open(QIODevice::WriteOnly | QIODevice::Truncate))
        return false;
    auto quoted = [](QString p) { return QLatin1Char('\'') + p.replace(QLatin1Char('\''), QStringLiteral("'\\''")) + QLatin1Char('\''); };
    QTextStream out(&file);
    for (const Frame &f : frames) {
        out << "file " << quoted(f.file) << "\n";
        out << "duration " << QString::number(double(f.hold) / fps, 'f', 6) << "\n";
    }
    // The concat demuxer ignores the last duration unless the file repeats;
    // callers cap the output with -frames:v.
    if (!frames.isEmpty())
        out << "file " << quoted(frames.last().file) << "\n";
    return true;
}
