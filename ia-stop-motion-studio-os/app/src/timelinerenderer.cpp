#include "timelinerenderer.h"
#include "formats.h"
#include "scene.h"
#include "timeline.h"

#include <QCryptographicHash>
#include <QDateTime>
#include <QDir>
#include <QFileInfo>
#include <QRegularExpression>
#include <QSaveFile>
#include <QXmlStreamWriter>

#include <numeric>

namespace {

const char *kRenderNode = "/dev/dri/renderD128";

void xmlProperty(QXmlStreamWriter &xml, const QString &name, const QString &value)
{
    xml.writeStartElement(QStringLiteral("property"));
    xml.writeAttribute(QStringLiteral("name"), name);
    xml.writeCharacters(value);
    xml.writeEndElement();
}

void transition(QXmlStreamWriter &xml, const QString &service, int a, int b, int in, int out,
                const QList<QPair<QString, QString>> &extra = {})
{
    xml.writeStartElement(QStringLiteral("transition"));
    xml.writeAttribute(QStringLiteral("in"), QString::number(in));
    xml.writeAttribute(QStringLiteral("out"), QString::number(out));
    xmlProperty(xml, QStringLiteral("mlt_service"), service);
    xmlProperty(xml, QStringLiteral("a_track"), QString::number(a));
    xmlProperty(xml, QStringLiteral("b_track"), QString::number(b));
    for (const auto &kv : extra)
        xmlProperty(xml, kv.first, kv.second);
    xml.writeEndElement();
}

void volumeFilter(QXmlStreamWriter &xml, double db)
{
    if (qFuzzyIsNull(db))
        return;
    xml.writeStartElement(QStringLiteral("filter"));
    xmlProperty(xml, QStringLiteral("mlt_service"), QStringLiteral("volume"));
    xmlProperty(xml, QStringLiteral("level"), QString::number(db, 'f', 2));
    xml.writeEndElement();
}

} // namespace

TimelineRenderer::TimelineRenderer(Timeline *timeline, QObject *parent)
    : QObject(parent)
    , m_timeline(timeline)
{
    m_process.setProcessChannelMode(QProcess::MergedChannels);
    connect(&m_process, &QProcess::finished, this, &TimelineRenderer::onProcessFinished);
    connect(&m_process, &QProcess::readyRead, this, [this] {
        const QString out = QString::fromUtf8(m_process.readAll());
        if (m_phase != Phase::Melt)
            return;
        static const QRegularExpression re(QStringLiteral("percentage:\\s*(\\d+)"));
        auto it = re.globalMatch(out);
        while (it.hasNext()) {
            m_progress = 0.2 + 0.8 * it.next().captured(1).toDouble() / 100.0;
            emit progressChanged();
        }
    });
}

QString TimelineRenderer::sceneCachePath(const QString &sceneDir) const
{
    // Keyed by the scene's manifest contents, so recaptures invalidate it.
    QFile manifest(sceneDir + QStringLiteral("/project.json"));
    manifest.open(QIODevice::ReadOnly);
    const QByteArray hash = QCryptographicHash::hash(manifest.readAll(), QCryptographicHash::Sha1).toHex().left(12);
    return sceneDir + QStringLiteral("/export/.cena_%1.mp4").arg(QString::fromLatin1(hash));
}

QString TimelineRenderer::writeProject(const QString &path)
{
    const QString file = path.isEmpty() ? m_timeline->workDir() + QStringLiteral("/filme.mlt") : path;
    QDir().mkpath(QFileInfo(file).absolutePath());
    const QSize size = m_timeline->frameSize();
    const int fps = m_timeline->fps();
    const int total = qMax(1, m_timeline->duration());
    const auto &video = m_timeline->videoList();
    const auto &titles = m_timeline->titleList();
    const auto &audio = m_timeline->audioList();

    QSaveFile out(file);
    if (!out.open(QIODevice::WriteOnly))
        return {};
    QXmlStreamWriter xml(&out);
    xml.setAutoFormatting(true);
    xml.writeStartDocument();
    xml.writeStartElement(QStringLiteral("mlt"));
    xml.writeAttribute(QStringLiteral("LC_NUMERIC"), QStringLiteral("C"));
    xml.writeAttribute(QStringLiteral("title"), QStringLiteral("IA Stop-Motion Studio OS"));

    const int g = std::gcd(size.width(), size.height());
    xml.writeStartElement(QStringLiteral("profile"));
    xml.writeAttribute(QStringLiteral("width"), QString::number(size.width()));
    xml.writeAttribute(QStringLiteral("height"), QString::number(size.height()));
    xml.writeAttribute(QStringLiteral("frame_rate_num"), QString::number(fps));
    xml.writeAttribute(QStringLiteral("frame_rate_den"), QStringLiteral("1"));
    xml.writeAttribute(QStringLiteral("progressive"), QStringLiteral("1"));
    xml.writeAttribute(QStringLiteral("sample_aspect_num"), QStringLiteral("1"));
    xml.writeAttribute(QStringLiteral("sample_aspect_den"), QStringLiteral("1"));
    xml.writeAttribute(QStringLiteral("display_aspect_num"), QString::number(size.width() / g));
    xml.writeAttribute(QStringLiteral("display_aspect_den"), QString::number(size.height() / g));
    xml.writeAttribute(QStringLiteral("colorspace"), QStringLiteral("709"));
    xml.writeEndElement();

    // producers
    xml.writeStartElement(QStringLiteral("producer"));
    xml.writeAttribute(QStringLiteral("id"), QStringLiteral("fundo"));
    xml.writeAttribute(QStringLiteral("in"), QStringLiteral("0"));
    xml.writeAttribute(QStringLiteral("out"), QString::number(total - 1));
    xmlProperty(xml, QStringLiteral("mlt_service"), QStringLiteral("color"));
    xmlProperty(xml, QStringLiteral("resource"), QStringLiteral("#FF000000"));
    xmlProperty(xml, QStringLiteral("length"), QString::number(total));
    xml.writeEndElement();

    for (const auto &c : video) {
        xml.writeStartElement(QStringLiteral("producer"));
        xml.writeAttribute(QStringLiteral("id"), QStringLiteral("v_") + c.id);
        if (c.type == QLatin1String("image")) {
            xml.writeAttribute(QStringLiteral("in"), QStringLiteral("0"));
            xml.writeAttribute(QStringLiteral("out"), QString::number(c.out - 1));
            xmlProperty(xml, QStringLiteral("resource"), c.source);
            xmlProperty(xml, QStringLiteral("mlt_service"), QStringLiteral("qimage"));
            xmlProperty(xml, QStringLiteral("length"), QString::number(c.out));
            xmlProperty(xml, QStringLiteral("ttl"), QStringLiteral("1"));
        } else {
            const QString resource = c.type == QLatin1String("scene") ? sceneCachePath(c.source) : c.source;
            xmlProperty(xml, QStringLiteral("resource"), resource);
            xmlProperty(xml, QStringLiteral("mlt_service"), QStringLiteral("avformat"));
        }
        volumeFilter(xml, c.volume);
        xml.writeEndElement();
    }
    for (const auto &t : titles) {
        xml.writeStartElement(QStringLiteral("producer"));
        xml.writeAttribute(QStringLiteral("id"), QStringLiteral("t_") + t.id);
        xml.writeAttribute(QStringLiteral("in"), QStringLiteral("0"));
        xml.writeAttribute(QStringLiteral("out"), QString::number(t.length - 1));
        xmlProperty(xml, QStringLiteral("resource"), t.image);
        xmlProperty(xml, QStringLiteral("mlt_service"), QStringLiteral("qimage"));
        xmlProperty(xml, QStringLiteral("length"), QString::number(t.length));
        xmlProperty(xml, QStringLiteral("ttl"), QStringLiteral("1"));
        xml.writeEndElement();
    }
    for (const auto &a : audio) {
        xml.writeStartElement(QStringLiteral("producer"));
        xml.writeAttribute(QStringLiteral("id"), QStringLiteral("a_") + a.id);
        xmlProperty(xml, QStringLiteral("resource"), a.source);
        xmlProperty(xml, QStringLiteral("mlt_service"), QStringLiteral("avformat"));
        volumeFilter(xml, a.volume);
        xml.writeEndElement();
    }

    auto blank = [&](int length) {
        if (length <= 0)
            return;
        xml.writeStartElement(QStringLiteral("blank"));
        xml.writeAttribute(QStringLiteral("length"), QString::number(length));
        xml.writeEndElement();
    };
    auto entry = [&](const QString &producer, int in, int out) {
        xml.writeStartElement(QStringLiteral("entry"));
        xml.writeAttribute(QStringLiteral("producer"), producer);
        xml.writeAttribute(QStringLiteral("in"), QString::number(in));
        xml.writeAttribute(QStringLiteral("out"), QString::number(out));
        xml.writeEndElement();
    };

    // Track 0: black background.
    xml.writeStartElement(QStringLiteral("playlist"));
    xml.writeAttribute(QStringLiteral("id"), QStringLiteral("trilha_fundo"));
    entry(QStringLiteral("fundo"), 0, total - 1);
    xml.writeEndElement();

    // Tracks 1 and 2: video clips alternate A/B so dissolves can overlap.
    for (int ab = 0; ab < 2; ++ab) {
        xml.writeStartElement(QStringLiteral("playlist"));
        xml.writeAttribute(QStringLiteral("id"), ab ? QStringLiteral("video_b") : QStringLiteral("video_a"));
        int pos = 0;
        for (int i = ab; i < video.size(); i += 2) {
            const auto &c = video.at(i);
            blank(c.start - pos);
            const int in = c.type == QLatin1String("image") ? 0 : c.in;
            entry(QStringLiteral("v_") + c.id, in, in + (c.out - c.in) - 1);
            pos = c.start + (c.out - c.in);
        }
        xml.writeEndElement();
    }
    // One track per title and per audio clip, so they may overlap freely.
    for (const auto &t : titles) {
        xml.writeStartElement(QStringLiteral("playlist"));
        xml.writeAttribute(QStringLiteral("id"), QStringLiteral("titulo_") + t.id);
        blank(t.start);
        entry(QStringLiteral("t_") + t.id, 0, t.length - 1);
        xml.writeEndElement();
    }
    for (const auto &a : audio) {
        xml.writeStartElement(QStringLiteral("playlist"));
        xml.writeAttribute(QStringLiteral("id"), QStringLiteral("audio_") + a.id);
        blank(a.start);
        entry(QStringLiteral("a_") + a.id, a.in, a.out - 1);
        xml.writeEndElement();
    }

    xml.writeStartElement(QStringLiteral("tractor"));
    xml.writeAttribute(QStringLiteral("id"), QStringLiteral("filme"));
    xml.writeAttribute(QStringLiteral("in"), QStringLiteral("0"));
    xml.writeAttribute(QStringLiteral("out"), QString::number(total - 1));
    xml.writeStartElement(QStringLiteral("multitrack"));
    auto track = [&](const QString &producer, bool audioOnly) {
        xml.writeStartElement(QStringLiteral("track"));
        xml.writeAttribute(QStringLiteral("producer"), producer);
        if (audioOnly)
            xml.writeAttribute(QStringLiteral("hide"), QStringLiteral("video"));
        xml.writeEndElement();
    };
    track(QStringLiteral("trilha_fundo"), false);
    track(QStringLiteral("video_a"), false);
    track(QStringLiteral("video_b"), false);
    for (const auto &t : titles)
        track(QStringLiteral("titulo_") + t.id, false);
    for (const auto &a : audio)
        track(QStringLiteral("audio_") + a.id, true);
    xml.writeEndElement(); // multitrack

    // Compositing: one affine per clip, only over its own range (a blank
    // track would otherwise paint black). A dissolve is an opacity ramp.
    const QString full = QStringLiteral("0 0 %1 %2").arg(size.width()).arg(size.height());
    for (int i = 0; i < video.size(); ++i) {
        const auto &c = video.at(i);
        QList<QPair<QString, QString>> extra{{QStringLiteral("distort"), QStringLiteral("0")}};
        if (c.transition > 0) {
            extra.append({QStringLiteral("rect"),
                          QStringLiteral("0=%1 0;%2=%1 1").arg(full).arg(c.transition - 1)});
        }
        transition(xml, QStringLiteral("affine"), 0, 1 + i % 2, c.start, c.start + (c.out - c.in) - 1, extra);
    }
    for (int i = 0; i < titles.size(); ++i) {
        const auto &t = titles.at(i);
        transition(xml, QStringLiteral("affine"), 0, 3 + i, t.start, t.start + t.length - 1);
    }
    // Audio: mix every track that can carry sound into track 0.
    QList<int> soundTracks{1, 2};
    for (int i = 0; i < audio.size(); ++i)
        soundTracks << 3 + int(titles.size()) + i;
    for (int b : soundTracks) {
        transition(xml, QStringLiteral("mix"), 0, b, 0, total - 1,
                   {{QStringLiteral("always_active"), QStringLiteral("1")}, {QStringLiteral("sum"), QStringLiteral("1")}});
    }
    xml.writeEndElement(); // tractor
    xml.writeEndElement(); // mlt
    xml.writeEndDocument();
    return out.commit() ? file : QString();
}

bool TimelineRenderer::render(bool preferHardware)
{
    if (m_busy)
        return false;
    if (m_timeline->duration() <= 0 || m_timeline->videoList().isEmpty()) {
        setStatus(tr("Adicione pelo menos uma cena ou vídeo à timeline."));
        return false;
    }
    m_preferHardware = preferHardware && QFileInfo::exists(QString::fromLatin1(kRenderNode));
    m_cancelled = false;
    m_progress = 0.0;
    emit progressChanged();

    m_pending.clear();
    QStringList seen;
    for (const auto &c : m_timeline->videoList()) {
        if (c.type != QLatin1String("scene") || seen.contains(c.source))
            continue;
        seen << c.source;
        const QString cache = sceneCachePath(c.source);
        if (!QFileInfo::exists(cache))
            m_pending.append({c.source, cache});
    }
    m_sceneCount = m_pending.size();
    setBusy(true);
    nextScene();
    return true;
}

void TimelineRenderer::nextScene()
{
    if (m_pending.isEmpty()) {
        m_projectFile = writeProject();
        if (m_projectFile.isEmpty()) {
            finish(false, tr("Falha ao escrever o projeto MLT."));
            return;
        }
        m_output = Formats::uniqueOutput(m_timeline->workDir(), QStringLiteral("filme"));
        startMelt(m_preferHardware);
        return;
    }

    const SceneJob job = m_pending.first();
    const Scene scene = Scene::load(job.dir);
    QDir().mkpath(QFileInfo(job.cache).absolutePath());
    // Old caches of this scene are stale now.
    for (const QFileInfo &f : QDir(QFileInfo(job.cache).absolutePath()).entryInfoList({QStringLiteral(".cena_*.mp4")}, QDir::Files | QDir::Hidden))
        QFile::remove(f.absoluteFilePath());
    const QString list = job.cache + QStringLiteral(".txt");
    scene.writeConcatList(list);

    const int done = m_sceneCount - int(m_pending.size());
    m_progress = 0.2 * done / qMax(1, m_sceneCount);
    emit progressChanged();
    setStatus(tr("Preparando cena %1 de %2: %3").arg(done + 1).arg(m_sceneCount).arg(scene.name));

    m_phase = Phase::Scenes;
    // Near-lossless intermediate at the scene's own frame rate.
    QStringList args{QStringLiteral("-y"), QStringLiteral("-hide_banner"), QStringLiteral("-loglevel"), QStringLiteral("error"),
                     QStringLiteral("-f"), QStringLiteral("concat"), QStringLiteral("-safe"), QStringLiteral("0"),
                     QStringLiteral("-i"), list};
    args << scene.audioInputArgs()
         << QStringLiteral("-vf") << scene.filterPrefix() + QStringLiteral("scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p")
         << QStringLiteral("-c:v") << QStringLiteral("libx264") << QStringLiteral("-preset") << QStringLiteral("veryfast")
         << QStringLiteral("-crf") << QStringLiteral("12")
         << scene.audioOutputArgs()
         << QStringLiteral("-fps_mode") << QStringLiteral("cfr") << QStringLiteral("-r") << QString::number(scene.fps)
         << QStringLiteral("-frames:v") << QString::number(scene.totalFrames());
    m_process.start(QStringLiteral("ffmpeg"), args << job.cache + QStringLiteral(".part.mp4"));
}

void TimelineRenderer::startMelt(bool hardware)
{
    m_hardware = hardware;
    m_phase = Phase::Melt;
    QStringList args{m_projectFile, QStringLiteral("-progress"),
                     QStringLiteral("-consumer"), QStringLiteral("avformat:") + m_output,
                     QStringLiteral("acodec=aac"), QStringLiteral("ab=192k"), QStringLiteral("ar=48000"),
                     QStringLiteral("movflags=+faststart"), QStringLiteral("real_time=-1")};
    if (hardware) {
        args << QStringLiteral("vcodec=h264_vaapi") << QStringLiteral("vaapi_device=") + QString::fromLatin1(kRenderNode)
             << QStringLiteral("vf=format=nv12,hwupload") << QStringLiteral("qp=20");
    } else {
        args << QStringLiteral("vcodec=libx264") << QStringLiteral("preset=medium") << QStringLiteral("crf=18")
             << QStringLiteral("pix_fmt=yuv420p");
    }
    setStatus(hardware ? tr("Renderizando o filme com a GPU (VAAPI)…") : tr("Renderizando o filme com a CPU (x264)…"));
    m_process.start(QStringLiteral("melt"), args);
    if (!m_process.waitForStarted(3000))
        finish(false, tr("MLT não encontrado. Instale com: sudo apt install melt"));
}

void TimelineRenderer::onProcessFinished(int exitCode, QProcess::ExitStatus status)
{
    const bool ok = status == QProcess::NormalExit && exitCode == 0 && !m_cancelled;
    if (m_cancelled) {
        finish(false, tr("Renderização cancelada."));
        return;
    }
    if (m_phase == Phase::Scenes) {
        const SceneJob job = m_pending.takeFirst();
        QFile::remove(job.cache + QStringLiteral(".txt"));
        if (!ok || !QFile::rename(job.cache + QStringLiteral(".part.mp4"), job.cache)) {
            QFile::remove(job.cache + QStringLiteral(".part.mp4"));
            finish(false, tr("Falha ao preparar a cena (FFmpeg)."));
            return;
        }
        nextScene();
        return;
    }
    if (!ok && m_hardware) {
        QFile::remove(m_output);
        startMelt(false);
        return;
    }
    if (!ok) {
        QFile::remove(m_output);
        finish(false, tr("Falha na renderização (melt código %1).").arg(exitCode));
        return;
    }
    m_progress = 1.0;
    emit progressChanged();
    finish(true, tr("Filme exportado: %1").arg(QFileInfo(m_output).fileName()));
}

void TimelineRenderer::cancel()
{
    if (!m_busy)
        return;
    m_cancelled = true;
    m_pending.clear();
    m_process.terminate();
    if (!m_process.waitForFinished(2000))
        m_process.kill();
}

void TimelineRenderer::finish(bool ok, const QString &message)
{
    m_phase = Phase::Idle;
    setStatus(message);
    setBusy(false);
    emit finished(ok, ok ? m_output : QString());
}

void TimelineRenderer::setStatus(const QString &status)
{
    if (m_status == status)
        return;
    m_status = status;
    emit statusChanged();
}

void TimelineRenderer::setBusy(bool busy)
{
    if (m_busy == busy)
        return;
    m_busy = busy;
    emit busyChanged();
}
