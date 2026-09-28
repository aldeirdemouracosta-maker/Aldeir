#include "projectmanager.h"

#include <QDateTime>
#include <QDir>
#include <QFileInfo>
#include <QImageCapture>
#include <QImageReader>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QRegularExpression>
#include <QSaveFile>
#include <QStandardPaths>

#include <algorithm>
#include <functional>

#include <unistd.h>

namespace {

QString defaultBaseDir()
{
    const QString env = qEnvironmentVariable("IA_SMS_HOME");
    if (!env.isEmpty())
        return env;
    return QDir::homePath() + QStringLiteral("/IA-StopMotion");
}

// QSaveFile renames atomically on commit; the explicit fsync makes sure the
// data reached the disk before the rename, so a power loss keeps the frame.
bool writeAtomically(const QString &path, const std::function<bool(QSaveFile &)> &writer)
{
    QSaveFile file(path);
    if (!file.open(QIODevice::WriteOnly))
        return false;
    if (!writer(file)) {
        file.cancelWriting();
        return false;
    }
    if (!file.flush())
        return false;
    ::fsync(file.handle());
    return file.commit();
}

QString sanitizeName(QString name)
{
    name = name.trimmed();
    name.replace(QRegularExpression(QStringLiteral("[/\\\\:*?\"<>|]")), QStringLiteral("-"));
    return name.isEmpty() ? QStringLiteral("Projeto sem nome") : name;
}

} // namespace

ProjectManager::ProjectManager(QObject *parent)
    : QObject(parent)
    , m_baseDir(defaultBaseDir())
{
    QDir().mkpath(m_baseDir + QStringLiteral("/Projetos"));
}

void ProjectManager::setFps(int fps)
{
    fps = qBound(1, fps, 60);
    if (fps == m_fps)
        return;
    m_fps = fps;
    emit fpsChanged();
    emit framesChanged();
    saveManifest();
}

QVariantList ProjectManager::frames() const
{
    QVariantList list;
    list.reserve(m_frames.size());
    for (const Frame &f : m_frames) {
        QUrl url = QUrl::fromLocalFile(m_path + QLatin1Char('/') + f.file);
        if (const int rev = m_revisions.value(f.file))
            url.setQuery(QStringLiteral("v=%1").arg(rev));
        list.append(QVariantMap{
            {QStringLiteral("url"), url},
            {QStringLiteral("hold"), f.hold},
            {QStringLiteral("edited"), QFileInfo::exists(m_path + QStringLiteral("/originais/") + QFileInfo(f.file).fileName())},
        });
    }
    return list;
}

int ProjectManager::totalFrames() const
{
    int total = 0;
    for (const Frame &f : m_frames)
        total += f.hold;
    return total;
}

QString ProjectManager::durationText() const
{
    const int seconds = m_fps > 0 ? totalFrames() / m_fps : 0;
    return QStringLiteral("%1:%2:%3")
        .arg(seconds / 3600, 2, 10, QLatin1Char('0'))
        .arg((seconds / 60) % 60, 2, 10, QLatin1Char('0'))
        .arg(seconds % 60, 2, 10, QLatin1Char('0'));
}

QString ProjectManager::resolutionText() const
{
    if (!m_resolution.isValid())
        return QStringLiteral("—");
    if (m_resolution.height() >= 2160)
        return QStringLiteral("4K");
    return QStringLiteral("%1p").arg(m_resolution.height());
}

QVariantList ProjectManager::recentProjects() const
{
    QDir dir(m_baseDir + QStringLiteral("/Projetos"));
    const auto entries = dir.entryInfoList(QDir::Dirs | QDir::NoDotAndDotDot, QDir::Time);
    QVariantList list;
    for (const QFileInfo &info : entries) {
        const QString manifest = info.absoluteFilePath() + QStringLiteral("/project.json");
        QFile file(manifest);
        if (!file.open(QIODevice::ReadOnly))
            continue;
        const QJsonObject obj = QJsonDocument::fromJson(file.readAll()).object();
        const QJsonArray frames = obj.value(QStringLiteral("frames")).toArray();
        QUrl thumb;
        if (!frames.isEmpty()) {
            thumb = QUrl::fromLocalFile(info.absoluteFilePath() + QLatin1Char('/')
                                        + frames.last().toObject().value(QStringLiteral("file")).toString());
        }
        list.append(QVariantMap{
            {QStringLiteral("name"), obj.value(QStringLiteral("name")).toString(info.fileName())},
            {QStringLiteral("path"), info.absoluteFilePath()},
            {QStringLiteral("frames"), frames.size()},
            {QStringLiteral("fps"), obj.value(QStringLiteral("fps")).toInt(12)},
            {QStringLiteral("thumbnail"), thumb},
        });
    }
    return list;
}

bool ProjectManager::newProject(const QString &name)
{
    const QString clean = sanitizeName(name);
    QString path = m_baseDir + QStringLiteral("/Projetos/") + clean;
    for (int i = 2; QFileInfo::exists(path); ++i)
        path = m_baseDir + QStringLiteral("/Projetos/") + clean + QStringLiteral(" (%1)").arg(i);

    if (!QDir().mkpath(path + QStringLiteral("/frames"))) {
        fail(tr("Não foi possível criar a pasta do projeto: %1").arg(path));
        return false;
    }
    m_name = QFileInfo(path).fileName();
    m_path = path;
    m_fps = 12;
    m_nextIndex = 1;
    m_resolution = {};
    m_frames.clear();
    m_audio.clear();
    m_audioOffset = 0;
    m_deflicker = false;
    m_plateNext = false;
    m_revisions.clear();
    m_mouthCenter = QPointF(0.5, 0.45);
    m_mouthWidth = 0.12; // keep m_character: new scenes usually star the same puppet
    saveManifest();
    emit projectChanged();
    emit fpsChanged();
    emit framesChanged();
    emit audioChanged();
    emit deflickerChanged();
    emit cleanPlateChanged();
    emit characterChanged();
    emit recentProjectsChanged();
    return true;
}

bool ProjectManager::openProject(const QString &path)
{
    const QString previousPath = m_path;
    m_path = QFileInfo(path).absoluteFilePath();
    if (!loadManifest()) {
        m_path = previousPath;
        fail(tr("Projeto inválido: %1").arg(path));
        return false;
    }
    emit projectChanged();
    emit fpsChanged();
    emit framesChanged();
    emit audioChanged();
    emit deflickerChanged();
    emit cleanPlateChanged();
    emit characterChanged();
    return true;
}

bool ProjectManager::loadManifest()
{
    QFile file(m_path + QStringLiteral("/project.json"));
    if (!file.open(QIODevice::ReadOnly))
        return false;
    const QJsonObject obj = QJsonDocument::fromJson(file.readAll()).object();
    if (obj.isEmpty())
        return false;

    m_name = obj.value(QStringLiteral("name")).toString(QFileInfo(m_path).fileName());
    m_fps = obj.value(QStringLiteral("fps")).toInt(12);
    m_nextIndex = obj.value(QStringLiteral("nextIndex")).toInt(1);
    m_audio = obj.value(QStringLiteral("audio")).toString();
    if (!m_audio.isEmpty() && !QFileInfo::exists(m_path + QLatin1Char('/') + m_audio))
        m_audio.clear();
    m_audioOffset = obj.value(QStringLiteral("audioOffset")).toInt(0);
    m_deflicker = obj.value(QStringLiteral("deflicker")).toBool(false);
    m_plateNext = false;
    m_revisions.clear();
    m_character = obj.value(QStringLiteral("personagem")).toString();
    {
        const QJsonObject boca = obj.value(QStringLiteral("boca")).toObject();
        m_mouthCenter = QPointF(boca.value(QStringLiteral("x")).toDouble(0.5), boca.value(QStringLiteral("y")).toDouble(0.45));
        m_mouthWidth = boca.value(QStringLiteral("largura")).toDouble(0.12);
    }
    m_frames.clear();
    for (const QJsonValue &v : obj.value(QStringLiteral("frames")).toArray()) {
        const QJsonObject f = v.toObject();
        const QString rel = f.value(QStringLiteral("file")).toString();
        // Frames whose file vanished (e.g. manual cleanup) are dropped instead
        // of breaking playback and export.
        if (QFileInfo::exists(m_path + QLatin1Char('/') + rel))
            m_frames.append({rel, qMax(1, f.value(QStringLiteral("hold")).toInt(1))});
    }
    m_resolution = {};
    if (!m_frames.isEmpty())
        m_resolution = QImageReader(m_path + QLatin1Char('/') + m_frames.first().file).size();
    return true;
}

bool ProjectManager::saveManifest()
{
    if (m_path.isEmpty())
        return false;
    QJsonArray frames;
    for (const Frame &f : m_frames)
        frames.append(QJsonObject{{QStringLiteral("file"), f.file}, {QStringLiteral("hold"), f.hold}});
    const QJsonObject obj{
        {QStringLiteral("name"), m_name},
        {QStringLiteral("fps"), m_fps},
        {QStringLiteral("nextIndex"), m_nextIndex},
        {QStringLiteral("audio"), m_audio},
        {QStringLiteral("audioOffset"), m_audioOffset},
        {QStringLiteral("deflicker"), m_deflicker},
        {QStringLiteral("personagem"), m_character},
        {QStringLiteral("boca"), QJsonObject{{QStringLiteral("x"), m_mouthCenter.x()}, {QStringLiteral("y"), m_mouthCenter.y()},
                                             {QStringLiteral("largura"), m_mouthWidth}}},
        {QStringLiteral("updated"), QDateTime::currentDateTime().toString(Qt::ISODate)},
        {QStringLiteral("frames"), frames},
    };
    const QByteArray data = QJsonDocument(obj).toJson();
    const bool ok = writeAtomically(m_path + QStringLiteral("/project.json"),
                                    [&](QSaveFile &f) { return f.write(data) == data.size(); });
    if (!ok)
        fail(tr("Falha ao salvar project.json"));
    return ok;
}

QString ProjectManager::nextFrameFileName() const
{
    return QStringLiteral("frames/frame_%1.png").arg(m_nextIndex, 6, 10, QLatin1Char('0'));
}

void ProjectManager::attachImageCapture(QObject *imageCapture)
{
    auto *capture = qobject_cast<QImageCapture *>(imageCapture);
    if (!capture || capture == m_capture)
        return;
    if (m_capture)
        disconnect(m_capture, nullptr, this, nullptr);
    m_capture = capture;
    connect(capture, &QImageCapture::imageCaptured, this,
            [this](int, const QImage &image) { ingestCapture(image); });
    connect(capture, &QImageCapture::errorOccurred, this,
            [this](int, QImageCapture::Error, const QString &msg) { fail(msg); });
}

bool ProjectManager::addFrame(const QImage &image)
{
    if (image.isNull())
        return false;
    if (m_path.isEmpty() && !newProject(QStringLiteral("Novo Projeto")))
        return false;

    const QString rel = nextFrameFileName();
    const bool ok = writeAtomically(m_path + QLatin1Char('/') + rel,
                                    [&](QSaveFile &f) { return image.save(&f, "PNG"); });
    if (!ok) {
        fail(tr("Falha ao gravar o quadro %1").arg(rel));
        return false;
    }
    ++m_nextIndex;
    m_frames.append({rel, 1});
    if (!m_resolution.isValid())
        m_resolution = image.size();
    saveManifest();
    emit framesChanged();
    emit frameSaved(m_frames.size() - 1);
    return true;
}

bool ProjectManager::ingestCapture(const QImage &image)
{
    if (m_plateNext) {
        m_plateNext = false;
        return setCleanPlate(image);
    }
    return addFrame(image);
}

int ProjectManager::importImages(const QList<QUrl> &urls)
{
    QList<QUrl> sorted = urls;
    std::sort(sorted.begin(), sorted.end(), [](const QUrl &a, const QUrl &b) {
        return QString::localeAwareCompare(a.fileName(), b.fileName()) < 0;
    });
    int imported = 0;
    for (const QUrl &url : sorted) {
        QImageReader reader(url.isLocalFile() ? url.toLocalFile() : url.toString());
        reader.setAutoTransform(true); // respect EXIF rotation from phones/cameras
        if (addFrame(reader.read()))
            ++imported;
    }
    return imported;
}

bool ProjectManager::deleteFrame(int index)
{
    if (index < 0 || index >= m_frames.size())
        return false;
    // Deleted frames go to a project-local trash so they can be recovered.
    const QString trash = m_path + QStringLiteral("/lixeira");
    QDir().mkpath(trash);
    const QString src = m_path + QLatin1Char('/') + m_frames.at(index).file;
    QFile::rename(src, trash + QLatin1Char('/') + QFileInfo(src).fileName());
    m_frames.removeAt(index);
    if (m_frames.isEmpty())
        m_resolution = {};
    saveManifest();
    emit framesChanged();
    return true;
}

bool ProjectManager::deleteLastFrame()
{
    return deleteFrame(m_frames.size() - 1);
}

void ProjectManager::setHold(int index, int hold)
{
    if (index < 0 || index >= m_frames.size())
        return;
    hold = qBound(1, hold, 24);
    if (m_frames[index].hold == hold)
        return;
    m_frames[index].hold = hold;
    saveManifest();
    emit framesChanged();
}

QUrl ProjectManager::frameUrl(int index) const
{
    if (index < 0 || index >= m_frames.size())
        return {};
    QUrl url = QUrl::fromLocalFile(frameFile(index));
    if (const int rev = m_revisions.value(m_frames.at(index).file))
        url.setQuery(QStringLiteral("v=%1").arg(rev));
    return url;
}

QString ProjectManager::frameFile(int index) const
{
    if (index < 0 || index >= m_frames.size())
        return {};
    return m_path + QLatin1Char('/') + m_frames.at(index).file;
}

int ProjectManager::holdAt(int index) const
{
    if (index < 0 || index >= m_frames.size())
        return 1;
    return m_frames.at(index).hold;
}

QString ProjectManager::audioFile() const
{
    return m_audio.isEmpty() ? QString() : m_path + QLatin1Char('/') + m_audio;
}

QString ProjectManager::audioName() const
{
    return m_audio.isEmpty() ? QString() : QFileInfo(m_audio).fileName();
}

void ProjectManager::setAudioOffset(int frames)
{
    frames = qMax(0, frames);
    if (frames == m_audioOffset)
        return;
    m_audioOffset = frames;
    saveManifest();
    emit audioChanged();
}

void ProjectManager::setDeflicker(bool on)
{
    if (on == m_deflicker)
        return;
    m_deflicker = on;
    saveManifest();
    emit deflickerChanged();
}

bool ProjectManager::setAudio(const QUrl &url)
{
    const QString src = url.isLocalFile() ? url.toLocalFile() : url.toString();
    if (!QFileInfo::exists(src)) {
        fail(tr("Arquivo de áudio não encontrado: %1").arg(src));
        return false;
    }
    if (m_path.isEmpty() && !newProject(QStringLiteral("Novo Projeto")))
        return false;
    QDir().mkpath(m_path + QStringLiteral("/audio"));
    QString rel = QStringLiteral("audio/") + QFileInfo(src).fileName();
    for (int i = 2; QFileInfo::exists(m_path + QLatin1Char('/') + rel) && QFileInfo(m_path + QLatin1Char('/') + rel) != QFileInfo(src); ++i)
        rel = QStringLiteral("audio/%1_%2.%3").arg(QFileInfo(src).completeBaseName()).arg(i).arg(QFileInfo(src).suffix());
    const QString dst = m_path + QLatin1Char('/') + rel;
    if (QFileInfo(dst) != QFileInfo(src) && !QFile::copy(src, dst)) {
        fail(tr("Falha ao copiar o áudio para o projeto."));
        return false;
    }
    m_audio = rel;
    saveManifest();
    emit audioChanged();
    return true;
}

void ProjectManager::removeAudio()
{
    if (m_audio.isEmpty())
        return;
    m_audio.clear();
    saveManifest();
    emit audioChanged();
}

QString ProjectManager::cleanPlateFile() const
{
    return m_path.isEmpty() ? QString() : m_path + QStringLiteral("/placa_limpa.png");
}

QUrl ProjectManager::cleanPlateUrl() const
{
    const QString file = cleanPlateFile();
    if (file.isEmpty() || !QFileInfo::exists(file))
        return {};
    QUrl url = QUrl::fromLocalFile(file);
    url.setQuery(QStringLiteral("v=%1").arg(m_plateRev));
    return url;
}

void ProjectManager::captureCleanPlateNext(bool on)
{
    m_plateNext = on;
    emit cleanPlateChanged();
}

bool ProjectManager::setCleanPlate(const QImage &image)
{
    if (image.isNull())
        return false;
    if (m_path.isEmpty() && !newProject(QStringLiteral("Novo Projeto")))
        return false;
    if (!writeAtomically(cleanPlateFile(), [&](QSaveFile &f) { return image.save(&f, "PNG"); })) {
        fail(tr("Falha ao gravar a placa limpa."));
        return false;
    }
    ++m_plateRev;
    emit cleanPlateChanged();
    return true;
}

bool ProjectManager::setCleanPlateFromFrame(int index)
{
    return setCleanPlate(QImage(frameFile(index)));
}

bool ProjectManager::setCleanPlateFromUrl(const QUrl &url)
{
    QImageReader reader(url.isLocalFile() ? url.toLocalFile() : url.toString());
    reader.setAutoTransform(true);
    return setCleanPlate(reader.read());
}

QString ProjectManager::originalFile(int index) const
{
    if (index < 0 || index >= m_frames.size())
        return {};
    return m_path + QStringLiteral("/originais/") + QFileInfo(m_frames.at(index).file).fileName();
}

bool ProjectManager::backupOriginal(int index)
{
    const QString backup = originalFile(index);
    if (backup.isEmpty())
        return false;
    if (QFileInfo::exists(backup))
        return true; // keep the very first original
    QDir().mkpath(QFileInfo(backup).absolutePath());
    return QFile::copy(frameFile(index), backup);
}

bool ProjectManager::hasOriginal(int index) const
{
    const QString backup = originalFile(index);
    return !backup.isEmpty() && QFileInfo::exists(backup);
}

bool ProjectManager::restoreOriginal(int index)
{
    if (!hasOriginal(index))
        return false;
    const QString target = frameFile(index);
    QFile::remove(target);
    if (!QFile::rename(originalFile(index), target))
        return false;
    framesModified({index});
    return true;
}

void ProjectManager::framesModified(const QList<int> &indices)
{
    for (int i : indices) {
        if (i >= 0 && i < m_frames.size())
            ++m_revisions[m_frames.at(i).file];
    }
    if (!m_frames.isEmpty())
        m_resolution = QImageReader(frameFile(0)).size();
    emit framesChanged();
}

void ProjectManager::setCharacterPath(const QString &path)
{
    if (path == m_character)
        return;
    m_character = path;
    saveManifest();
    emit characterChanged();
}

void ProjectManager::setMouthCenter(const QPointF &c)
{
    const QPointF clamped(qBound(0.0, c.x(), 1.0), qBound(0.0, c.y(), 1.0));
    if (clamped == m_mouthCenter)
        return;
    m_mouthCenter = clamped;
    saveManifest();
    emit characterChanged();
}

void ProjectManager::setMouthWidth(double w)
{
    w = qBound(0.02, w, 0.8);
    if (qFuzzyCompare(w, m_mouthWidth))
        return;
    m_mouthWidth = w;
    saveManifest();
    emit characterChanged();
}

void ProjectManager::fail(const QString &message)
{
    m_lastError = message;
    qWarning("%s", qPrintable(message));
    emit errorOccurred(message);
}
