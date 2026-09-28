#include "scene.h"

#include <QFile>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QStringList>
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
    const QString audio = obj.value(QStringLiteral("audio")).toString();
    if (!audio.isEmpty() && QFileInfo::exists(scene.dir + QLatin1Char('/') + audio))
        scene.audio = scene.dir + QLatin1Char('/') + audio;
    scene.audioOffset = qMax(0, obj.value(QStringLiteral("audioOffset")).toInt(0));
    scene.deflicker = obj.value(QStringLiteral("deflicker")).toBool(false);
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

QString Scene::filterPrefix() const
{
    // Evens out exposure changes between photos (lamps, daylight, auto
    // exposure) by averaging brightness over a 5-photo window.
    return deflicker ? QStringLiteral("deflicker=mode=pm:size=5,") : QString();
}

QStringList Scene::audioInputArgs() const
{
    if (audio.isEmpty())
        return {};
    QStringList args;
    if (audioOffset > 0)
        args << QStringLiteral("-itsoffset") << QString::number(double(audioOffset) / fps, 'f', 6);
    args << QStringLiteral("-i") << audio;
    return args;
}

QStringList Scene::audioOutputArgs() const
{
    if (audio.isEmpty())
        return {QStringLiteral("-an")};
    return {QStringLiteral("-map"), QStringLiteral("0:v:0"), QStringLiteral("-map"), QStringLiteral("1:a:0"),
            // Pad with silence if the audio is shorter, cut it if longer. (An
            // output -t would also drop the concat list's closing entry and
            // with it the last photo's hold; -frames:v bounds the video.)
            QStringLiteral("-af"), QStringLiteral("apad,atrim=end=%1").arg(seconds(), 0, 'f', 6),
            QStringLiteral("-c:a"), QStringLiteral("aac"), QStringLiteral("-b:a"), QStringLiteral("192k")};
}
