#include "timeline.h"
#include "formats.h"
#include "projectmanager.h"
#include "titlerenderer.h"

#include <QDir>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QProcess>
#include <QSaveFile>
#include <QUuid>

#include <algorithm>

namespace {

const QStringList kImageExt{QStringLiteral("png"), QStringLiteral("jpg"), QStringLiteral("jpeg"),
                            QStringLiteral("webp"), QStringLiteral("bmp")};
const QStringList kAudioExt{QStringLiteral("wav"), QStringLiteral("mp3"), QStringLiteral("ogg"),
                            QStringLiteral("flac"), QStringLiteral("m4a"), QStringLiteral("aac"), QStringLiteral("opus")};

} // namespace

Timeline::Timeline(ProjectManager *project, QObject *parent)
    : QObject(parent)
    , m_project(project)
{
    connect(project, &ProjectManager::projectChanged, this, &Timeline::load);
    // Recapturing a scene changes its length; refresh clips that use it.
    connect(project, &ProjectManager::framesChanged, this, [this] {
        m_sceneCache.remove(m_project->projectPath());
        reload();
    });
    connect(project, &ProjectManager::recentProjectsChanged, this, &Timeline::scenesChanged);
    load();
}

QString Timeline::newId()
{
    return QUuid::createUuid().toString(QUuid::Id128).left(8);
}

QString Timeline::filePath() const
{
    return m_project->projectPath().isEmpty() ? QString() : m_project->projectPath() + QStringLiteral("/timeline.json");
}

QString Timeline::workDir() const
{
    return m_project->projectPath() + QStringLiteral("/export");
}

void Timeline::setFps(int fps)
{
    fps = qBound(1, fps, 60);
    if (fps == m_fps)
        return;
    checkpoint(QString());
    // Keep every clip at the same place in seconds.
    const double k = double(fps) / m_fps;
    auto scale = [k](int v) { return int(qRound(v * k)); };
    for (VideoClip &c : m_video) {
        c.in = scale(c.in); c.out = scale(c.out); c.transition = scale(c.transition);
        c.sourceLength = scale(c.sourceLength);
    }
    for (Title &t : m_titles) { t.start = scale(t.start); t.length = qMax(1, scale(t.length)); }
    for (AudioClip &a : m_audio) {
        a.start = scale(a.start); a.in = scale(a.in); a.out = scale(a.out); a.sourceLength = scale(a.sourceLength);
    }
    m_fps = fps;
    touch();
}

void Timeline::setFormat(const QString &format)
{
    if (!Formats::ids().contains(format) || format == m_format)
        return;
    checkpoint(QString());
    m_format = format;
    for (Title &t : m_titles)
        renderTitleImage(t);
    touch();
}

QSize Timeline::frameSize() const
{
    return Formats::size(m_format);
}

const Scene &Timeline::scene(const QString &dir)
{
    auto it = m_sceneCache.find(dir);
    if (it == m_sceneCache.end())
        it = m_sceneCache.insert(dir, Scene::load(dir));
    return it.value();
}

int Timeline::probeFrames(const QString &file) const
{
    QProcess p;
    p.start(QStringLiteral("ffprobe"), {QStringLiteral("-v"), QStringLiteral("error"),
                                        QStringLiteral("-show_entries"), QStringLiteral("format=duration"),
                                        QStringLiteral("-of"), QStringLiteral("csv=p=0"), file});
    if (!p.waitForFinished(10000))
        return 0;
    const double seconds = QString::fromUtf8(p.readAllStandardOutput()).trimmed().toDouble();
    return int(seconds * m_fps);
}

QVariantList Timeline::availableScenes() const
{
    QVariantList list;
    for (const QVariant &v : m_project->recentProjects()) {
        const QVariantMap p = v.toMap();
        if (p.value(QStringLiteral("frames")).toInt() > 0)
            list.append(p);
    }
    return list;
}

// ── persistence ──────────────────────────────────────────────────────────

void Timeline::load()
{
    m_undo.clear();
    m_redo.clear();
    QJsonObject obj;
    QFile file(filePath());
    if (!filePath().isEmpty() && file.open(QIODevice::ReadOnly))
        obj = QJsonDocument::fromJson(file.readAll()).object();
    fromJson(obj);
    for (Title &t : m_titles)
        renderTitleImage(t);
    reload();
    emit undoStateChanged();
}

void Timeline::fromJson(const QJsonObject &obj)
{
    m_video.clear();
    m_titles.clear();
    m_audio.clear();
    m_sceneCache.clear();
    m_fps = qBound(1, obj.value(QStringLiteral("fps")).toInt(24), 60);
    m_format = obj.value(QStringLiteral("format")).toString(QStringLiteral("youtube"));
    for (const QJsonValue &v : obj.value(QStringLiteral("video")).toArray()) {
        const QJsonObject o = v.toObject();
        VideoClip c;
        c.id = o.value(QStringLiteral("id")).toString(newId());
        c.type = o.value(QStringLiteral("type")).toString();
        c.source = o.value(QStringLiteral("source")).toString();
        c.name = o.value(QStringLiteral("name")).toString();
        c.in = o.value(QStringLiteral("in")).toInt();
        c.out = o.value(QStringLiteral("out")).toInt();
        c.sourceLength = o.value(QStringLiteral("sourceLength")).toInt();
        c.transition = o.value(QStringLiteral("transition")).toInt();
        c.volume = o.value(QStringLiteral("volume")).toDouble();
        m_video.append(c);
    }
    for (const QJsonValue &v : obj.value(QStringLiteral("titles")).toArray()) {
        const QJsonObject o = v.toObject();
        Title t;
        t.id = o.value(QStringLiteral("id")).toString(newId());
        t.text = o.value(QStringLiteral("text")).toString();
        t.start = o.value(QStringLiteral("start")).toInt();
        t.length = qMax(1, o.value(QStringLiteral("length")).toInt(72));
        t.position = o.value(QStringLiteral("position")).toString(t.position);
        t.size = o.value(QStringLiteral("size")).toInt(8);
        t.color = o.value(QStringLiteral("color")).toString(t.color);
        t.box = o.value(QStringLiteral("box")).toBool(true);
        t.kind = o.value(QStringLiteral("kind")).toString();
        m_titles.append(t);
    }
    for (const QJsonValue &v : obj.value(QStringLiteral("audio")).toArray()) {
        const QJsonObject o = v.toObject();
        AudioClip a;
        a.id = o.value(QStringLiteral("id")).toString(newId());
        a.source = o.value(QStringLiteral("source")).toString();
        a.name = o.value(QStringLiteral("name")).toString();
        a.start = o.value(QStringLiteral("start")).toInt();
        a.in = o.value(QStringLiteral("in")).toInt();
        a.out = o.value(QStringLiteral("out")).toInt();
        a.sourceLength = o.value(QStringLiteral("sourceLength")).toInt();
        a.volume = o.value(QStringLiteral("volume")).toDouble();
        m_audio.append(a);
    }
}

void Timeline::reload()
{
    // Scenes may have been recaptured: clamp clips to their new length.
    m_sceneCache.clear();
    for (VideoClip &c : m_video) {
        if (c.type != QLatin1String("scene"))
            continue;
        const int length = int(qRound(scene(c.source).seconds() * m_fps));
        const bool wasFull = c.out >= c.sourceLength;
        c.sourceLength = length;
        if (wasFull || c.out > length)
            c.out = length;
        c.in = qMin(c.in, qMax(0, c.out - 1));
    }
    relayout();
    emit changed();
}

QJsonObject Timeline::toJson() const
{
    QJsonArray video, titles, audio;
    for (const VideoClip &c : m_video) {
        video.append(QJsonObject{{QStringLiteral("id"), c.id}, {QStringLiteral("type"), c.type},
                                 {QStringLiteral("source"), c.source}, {QStringLiteral("name"), c.name},
                                 {QStringLiteral("in"), c.in}, {QStringLiteral("out"), c.out},
                                 {QStringLiteral("sourceLength"), c.sourceLength},
                                 {QStringLiteral("transition"), c.transition}, {QStringLiteral("volume"), c.volume}});
    }
    for (const Title &t : m_titles) {
        titles.append(QJsonObject{{QStringLiteral("id"), t.id}, {QStringLiteral("text"), t.text},
                                  {QStringLiteral("start"), t.start}, {QStringLiteral("length"), t.length},
                                  {QStringLiteral("position"), t.position}, {QStringLiteral("size"), t.size},
                                  {QStringLiteral("color"), t.color}, {QStringLiteral("box"), t.box},
                                  {QStringLiteral("kind"), t.kind}});
    }
    for (const AudioClip &a : m_audio) {
        audio.append(QJsonObject{{QStringLiteral("id"), a.id}, {QStringLiteral("source"), a.source},
                                 {QStringLiteral("name"), a.name}, {QStringLiteral("start"), a.start},
                                 {QStringLiteral("in"), a.in}, {QStringLiteral("out"), a.out},
                                 {QStringLiteral("sourceLength"), a.sourceLength}, {QStringLiteral("volume"), a.volume}});
    }
    return QJsonObject{
        {QStringLiteral("fps"), m_fps}, {QStringLiteral("format"), m_format},
        {QStringLiteral("video"), video}, {QStringLiteral("titles"), titles}, {QStringLiteral("audio"), audio},
    };
}

void Timeline::save()
{
    if (filePath().isEmpty())
        return;
    const QByteArray data = QJsonDocument(toJson()).toJson();
    QSaveFile file(filePath());
    if (!file.open(QIODevice::WriteOnly) || file.write(data) != data.size() || !file.commit())
        emit errorOccurred(tr("Falha ao salvar timeline.json"));
}

// ── undo / redo ──────────────────────────────────────────────────────────

void Timeline::checkpoint(const QString &tag)
{
    // Continuous edits (a slider being dragged) collapse into one step.
    if (!tag.isEmpty() && tag == m_lastTag && m_lastCheckpoint.isValid() && m_lastCheckpoint.elapsed() < 1500) {
        m_lastCheckpoint.restart();
        return;
    }
    m_lastTag = tag;
    m_lastCheckpoint.restart();
    m_undo.append(toJson());
    if (m_undo.size() > 100)
        m_undo.removeFirst();
    m_redo.clear();
    emit undoStateChanged();
}

void Timeline::restore(const QJsonObject &state)
{
    fromJson(state);
    for (Title &t : m_titles)
        renderTitleImage(t);
    m_lastTag.clear();
    reload();
    save();
    emit undoStateChanged();
}

void Timeline::undo()
{
    if (m_undo.isEmpty())
        return;
    m_redo.append(toJson());
    restore(m_undo.takeLast());
}

void Timeline::redo()
{
    if (m_redo.isEmpty())
        return;
    m_undo.append(toJson());
    restore(m_redo.takeLast());
}

void Timeline::relayout()
{
    int pos = 0;
    for (int i = 0; i < m_video.size(); ++i) {
        VideoClip &c = m_video[i];
        const int len = c.out - c.in;
        if (i == 0) {
            c.transition = 0;
        } else {
            const int prevLen = m_video.at(i - 1).out - m_video.at(i - 1).in;
            c.transition = qBound(0, c.transition, qMin(prevLen, len) / 2);
        }
        c.start = pos - c.transition;
        pos = c.start + len;
    }
}

void Timeline::touch()
{
    relayout();
    save();
    emit changed();
}

void Timeline::renderTitleImage(Title &t)
{
    if (m_project->projectPath().isEmpty())
        return;
    const QString dir = workDir() + QStringLiteral("/titulos");
    QDir().mkpath(dir);
    t.image = dir + QStringLiteral("/%1_%2.png").arg(t.id, m_format);
    TitleRenderer::render(t.text, frameSize(), t.position, t.size, QColor(t.color), t.box).save(t.image);
}

// ── editing ──────────────────────────────────────────────────────────────

bool Timeline::addScene(const QString &projectDir)
{
    const Scene &s = scene(QFileInfo(projectDir).absoluteFilePath());
    if (!s.isValid()) {
        emit errorOccurred(tr("A cena não tem quadros."));
        return false;
    }
    checkpoint(QString());
    VideoClip c;
    c.id = newId();
    c.type = QStringLiteral("scene");
    c.source = s.dir;
    c.name = s.name;
    c.sourceLength = int(qRound(s.seconds() * m_fps));
    c.out = c.sourceLength;
    m_video.append(c);
    touch();
    return true;
}

int Timeline::addMedia(const QList<QUrl> &urls, int atFrame)
{
    checkpoint(QString());
    int added = 0;
    for (const QUrl &url : urls) {
        const QString file = url.isLocalFile() ? url.toLocalFile() : url.toString();
        const QString ext = QFileInfo(file).suffix().toLower();
        if (kAudioExt.contains(ext)) {
            AudioClip a;
            a.id = newId();
            a.source = file;
            a.name = QFileInfo(file).completeBaseName();
            a.start = atFrame >= 0 ? atFrame : 0;
            a.sourceLength = probeFrames(file);
            a.out = a.sourceLength > 0 ? a.sourceLength : 5 * m_fps;
            m_audio.append(a);
        } else {
            VideoClip c;
            c.id = newId();
            c.source = file;
            c.name = QFileInfo(file).completeBaseName();
            if (kImageExt.contains(ext)) {
                c.type = QStringLiteral("image");
                c.out = 3 * m_fps;
            } else {
                c.type = QStringLiteral("video");
                c.sourceLength = probeFrames(file);
                c.out = c.sourceLength > 0 ? c.sourceLength : 5 * m_fps;
            }
            m_video.append(c);
        }
        ++added;
    }
    if (added)
        touch();
    return added;
}

void Timeline::addTitle(const QString &text, int atFrame)
{
    checkpoint(QString());
    Title t;
    t.id = newId();
    t.text = text;
    t.start = qMax(0, atFrame);
    t.length = 3 * m_fps;
    renderTitleImage(t);
    m_titles.append(t);
    touch();
}

QStringList Timeline::speechSources()
{
    QStringList files;
    for (const VideoClip &c : std::as_const(m_video)) {
        if (c.type == QLatin1String("video"))
            files << c.source;
        else if (c.type == QLatin1String("scene") && !scene(c.source).audio.isEmpty())
            files << scene(c.source).audio;
    }
    for (const AudioClip &a : std::as_const(m_audio))
        files << a.source;
    files.removeDuplicates();
    return files;
}

int Timeline::subtitleCount() const
{
    return int(std::count_if(m_titles.begin(), m_titles.end(), [](const Title &t) { return t.kind == QLatin1String("legenda"); }));
}

int Timeline::setSubtitles(const QVariantMap &transcripts)
{
    checkpoint(QString());
    m_titles.erase(std::remove_if(m_titles.begin(), m_titles.end(),
                                  [](const Title &t) { return t.kind == QLatin1String("legenda"); }),
                   m_titles.end());

    // Places one source's segments; `offset` shifts audio seconds into the
    // clip's source time; [in, out) is the part of the source that is used.
    auto place = [&](const QString &file, double offset, int clipStart, int in, int out) {
        for (const QVariant &v : transcripts.value(file).toList()) {
            const QVariantMap seg = v.toMap();
            const int fs = int(qRound((seg.value(QStringLiteral("start")).toDouble() + offset) * m_fps));
            const int fe = int(qRound((seg.value(QStringLiteral("end")).toDouble() + offset) * m_fps));
            const int a = qMax(fs, in), b = qMin(fe, out);
            if (b <= a)
                continue;
            Title t;
            t.id = newId();
            t.kind = QStringLiteral("legenda");
            t.text = seg.value(QStringLiteral("text")).toString().trimmed();
            t.start = clipStart + (a - in);
            t.length = b - a;
            t.size = 6;
            renderTitleImage(t);
            m_titles.append(t);
        }
    };
    for (const VideoClip &c : std::as_const(m_video)) {
        if (c.type == QLatin1String("video")) {
            place(c.source, 0.0, c.start, c.in, c.out);
        } else if (c.type == QLatin1String("scene")) {
            const Scene &sc = scene(c.source);
            if (!sc.audio.isEmpty())
                place(sc.audio, double(sc.audioOffset) / sc.fps, c.start, c.in, c.out);
        }
    }
    for (const AudioClip &a : std::as_const(m_audio))
        place(a.source, 0.0, a.start, a.in, a.out);
    std::sort(m_titles.begin(), m_titles.end(), [](const Title &x, const Title &y) { return x.start < y.start; });
    touch();
    return subtitleCount();
}

void Timeline::moveClipTo(int from, int to)
{
    to = qBound(0, to, int(m_video.size()) - 1);
    if (from < 0 || from >= m_video.size() || from == to)
        return;
    checkpoint(QString());
    m_video.move(from, to);
    touch();
}

void Timeline::moveClip(int index, int delta)
{
    const int to = index + delta;
    if (index < 0 || index >= m_video.size() || to < 0 || to >= m_video.size())
        return;
    checkpoint(QString());
    m_video.move(index, to);
    touch();
}

void Timeline::removeVideo(int index)
{
    if (index < 0 || index >= m_video.size())
        return;
    checkpoint(QString());
    m_video.removeAt(index);
    touch();
}

void Timeline::removeTitle(int index)
{
    if (index < 0 || index >= m_titles.size())
        return;
    checkpoint(QString());
    QFile::remove(m_titles.at(index).image);
    m_titles.removeAt(index);
    touch();
}

void Timeline::removeAudio(int index)
{
    if (index < 0 || index >= m_audio.size())
        return;
    checkpoint(QString());
    m_audio.removeAt(index);
    touch();
}

bool Timeline::splitAt(int frame)
{
    for (int i = 0; i < m_video.size(); ++i) {
        VideoClip &c = m_video[i];
        const int local = frame - c.start;
        if (local <= 0 || local >= c.out - c.in)
            continue;
        checkpoint(QString());
        VideoClip &clip = m_video[i]; // re-fetch: checkpoint does not touch the list
        VideoClip second = clip;
        second.id = newId();
        second.in = clip.in + local;
        second.transition = 0;
        clip.out = clip.in + local;
        m_video.insert(i + 1, second);
        touch();
        return true;
    }
    return false;
}

void Timeline::setVideoProperty(int index, const QString &key, const QVariant &value)
{
    if (index < 0 || index >= m_video.size())
        return;
    checkpoint(QStringLiteral("v%1:%2").arg(index).arg(key));
    VideoClip &c = m_video[index];
    const int limit = c.sourceLength > 0 ? c.sourceLength : 3600 * m_fps;
    if (key == QLatin1String("in"))
        c.in = qBound(0, value.toInt(), c.out - 1);
    else if (key == QLatin1String("out"))
        c.out = qBound(c.in + 1, value.toInt(), limit);
    else if (key == QLatin1String("length"))
        c.out = qBound(c.in + 1, c.in + value.toInt(), limit);
    else if (key == QLatin1String("transition"))
        c.transition = qMax(0, value.toInt());
    else if (key == QLatin1String("volume"))
        c.volume = qBound(-60.0, value.toDouble(), 12.0);
    else if (key == QLatin1String("name"))
        c.name = value.toString();
    touch();
}

void Timeline::setTitleProperty(int index, const QString &key, const QVariant &value)
{
    if (index < 0 || index >= m_titles.size())
        return;
    checkpoint(QStringLiteral("t%1:%2").arg(index).arg(key));
    Title &t = m_titles[index];
    if (key == QLatin1String("text"))
        t.text = value.toString();
    else if (key == QLatin1String("start"))
        t.start = qMax(0, value.toInt());
    else if (key == QLatin1String("length"))
        t.length = qMax(1, value.toInt());
    else if (key == QLatin1String("position"))
        t.position = value.toString();
    else if (key == QLatin1String("size"))
        t.size = qBound(2, value.toInt(), 30);
    else if (key == QLatin1String("color"))
        t.color = value.toString();
    else if (key == QLatin1String("box"))
        t.box = value.toBool();
    renderTitleImage(t);
    touch();
}

void Timeline::setAudioProperty(int index, const QString &key, const QVariant &value)
{
    if (index < 0 || index >= m_audio.size())
        return;
    checkpoint(QStringLiteral("a%1:%2").arg(index).arg(key));
    AudioClip &a = m_audio[index];
    const int limit = a.sourceLength > 0 ? a.sourceLength : 3600 * m_fps;
    if (key == QLatin1String("start"))
        a.start = qMax(0, value.toInt());
    else if (key == QLatin1String("in"))
        a.in = qBound(0, value.toInt(), a.out - 1);
    else if (key == QLatin1String("length"))
        a.out = qBound(a.in + 1, a.in + value.toInt(), limit);
    else if (key == QLatin1String("volume"))
        a.volume = qBound(-60.0, value.toDouble(), 12.0);
    touch();
}

// ── read access for QML ──────────────────────────────────────────────────

int Timeline::duration() const
{
    int end = 0;
    if (!m_video.isEmpty())
        end = m_video.last().start + m_video.last().out - m_video.last().in;
    for (const Title &t : m_titles)
        end = qMax(end, t.start + t.length);
    for (const AudioClip &a : m_audio)
        end = qMax(end, a.start + a.out - a.in);
    return end;
}

QVariantList Timeline::videoClips() const
{
    QVariantList list;
    for (const VideoClip &c : m_video) {
        QUrl thumb;
        if (c.type == QLatin1String("scene")) {
            const Scene &s = const_cast<Timeline *>(this)->scene(c.source);
            const int idx = s.frameIndexAt(double(c.in) / m_fps);
            if (idx >= 0)
                thumb = QUrl::fromLocalFile(s.frames.at(idx).file);
        } else if (c.type == QLatin1String("image")) {
            thumb = QUrl::fromLocalFile(c.source);
        }
        list.append(QVariantMap{
            {QStringLiteral("id"), c.id}, {QStringLiteral("type"), c.type}, {QStringLiteral("name"), c.name},
            {QStringLiteral("source"), c.source}, {QStringLiteral("start"), c.start},
            {QStringLiteral("length"), c.out - c.in}, {QStringLiteral("in"), c.in}, {QStringLiteral("out"), c.out},
            {QStringLiteral("sourceLength"), c.sourceLength}, {QStringLiteral("transition"), c.transition},
            {QStringLiteral("volume"), c.volume}, {QStringLiteral("thumbnail"), thumb},
        });
    }
    return list;
}

QVariantList Timeline::titles() const
{
    QVariantList list;
    for (const Title &t : m_titles) {
        list.append(QVariantMap{
            {QStringLiteral("id"), t.id}, {QStringLiteral("text"), t.text}, {QStringLiteral("start"), t.start},
            {QStringLiteral("length"), t.length}, {QStringLiteral("position"), t.position},
            {QStringLiteral("size"), t.size}, {QStringLiteral("color"), t.color}, {QStringLiteral("box"), t.box},
            {QStringLiteral("image"), QUrl::fromLocalFile(t.image)},
            {QStringLiteral("kind"), t.kind},
        });
    }
    return list;
}

QVariantList Timeline::audioClips() const
{
    QVariantList list;
    for (const AudioClip &a : m_audio) {
        list.append(QVariantMap{
            {QStringLiteral("id"), a.id}, {QStringLiteral("name"), a.name}, {QStringLiteral("source"), QUrl::fromLocalFile(a.source)},
            {QStringLiteral("start"), a.start}, {QStringLiteral("length"), a.out - a.in}, {QStringLiteral("in"), a.in},
            {QStringLiteral("sourceLength"), a.sourceLength}, {QStringLiteral("volume"), a.volume},
        });
    }
    return list;
}

QVariantList Timeline::layersAt(int frame)
{
    QVariantList layers;
    for (int i = 0; i < m_video.size(); ++i) {
        const VideoClip &c = m_video.at(i);
        const int local = frame - c.start;
        if (local < 0 || local >= c.out - c.in)
            continue;
        const double opacity = c.transition > 0 && local < c.transition ? double(local + 1) / (c.transition + 1) : 1.0;
        const double seconds = double(c.in + local) / m_fps;
        QVariantMap layer{{QStringLiteral("kind"), c.type}, {QStringLiteral("opacity"), opacity},
                          {QStringLiteral("seconds"), seconds}, {QStringLiteral("clip"), i}};
        if (c.type == QLatin1String("scene")) {
            const Scene &s = scene(c.source);
            const int idx = s.frameIndexAt(seconds);
            layer.insert(QStringLiteral("url"), idx >= 0 ? QUrl::fromLocalFile(s.frames.at(idx).file) : QUrl());
        } else {
            layer.insert(QStringLiteral("url"), QUrl::fromLocalFile(c.source));
        }
        layers.append(layer);
    }
    for (const Title &t : m_titles) {
        if (frame >= t.start && frame < t.start + t.length) {
            layers.append(QVariantMap{{QStringLiteral("kind"), QStringLiteral("title")},
                                      {QStringLiteral("url"), QUrl::fromLocalFile(t.image)},
                                      {QStringLiteral("opacity"), 1.0}});
        }
    }
    return layers;
}

QString Timeline::timecode(int frame) const
{
    frame = qMax(0, frame);
    const int seconds = frame / m_fps;
    return QStringLiteral("%1:%2.%3")
        .arg(seconds / 60, 2, 10, QLatin1Char('0'))
        .arg(seconds % 60, 2, 10, QLatin1Char('0'))
        .arg(frame % m_fps, 2, 10, QLatin1Char('0'));
}
