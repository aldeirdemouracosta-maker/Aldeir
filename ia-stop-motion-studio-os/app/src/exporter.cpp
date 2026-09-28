#include "exporter.h"
#include "projectmanager.h"

#include <QDateTime>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QRegularExpression>
#include <QSize>
#include <QTextStream>

namespace {

const char *kRenderNode = "/dev/dri/renderD128";

QSize presetSize(const QString &preset)
{
    if (preset == QLatin1String("vertical"))
        return {1080, 1920};
    if (preset == QLatin1String("quadrado"))
        return {1080, 1080};
    if (preset == QLatin1String("4k"))
        return {3840, 2160};
    return {1920, 1080};
}

QString escapeConcatPath(QString path)
{
    return path.replace(QLatin1Char('\''), QStringLiteral("'\\''"));
}

} // namespace

Exporter::Exporter(ProjectManager *project, QObject *parent)
    : QObject(parent)
    , m_project(project)
{
    m_process.setProcessChannelMode(QProcess::MergedChannels);
    connect(&m_process, &QProcess::stateChanged, this, &Exporter::busyChanged);
    connect(&m_process, &QProcess::finished, this, &Exporter::onFinished);
    connect(&m_process, &QProcess::readyRead, this, [this] {
        const QString out = QString::fromUtf8(m_process.readAll());
        static const QRegularExpression re(QStringLiteral("out_time_us=(\\d+)"));
        auto it = re.globalMatch(out);
        while (it.hasNext()) {
            const double seconds = it.next().captured(1).toDouble() / 1e6;
            if (m_totalSeconds > 0) {
                m_progress = qBound(0.0, seconds / m_totalSeconds, 1.0);
                emit progressChanged();
            }
        }
    });
}

bool Exporter::vaapiAvailable() const
{
    return QFileInfo::exists(QString::fromLatin1(kRenderNode));
}

QStringList Exporter::presets() const
{
    return {QStringLiteral("youtube"), QStringLiteral("vertical"), QStringLiteral("quadrado"), QStringLiteral("4k")};
}

bool Exporter::writeConcatList(const QString &path) const
{
    QFile file(path);
    if (!file.open(QIODevice::WriteOnly | QIODevice::Truncate))
        return false;
    QTextStream out(&file);
    const int fps = qMax(1, m_project->fps());
    const int count = m_project->frameCount();
    for (int i = 0; i < count; ++i) {
        out << "file '" << escapeConcatPath(m_project->frameFile(i)) << "'\n";
        out << "duration " << QString::number(double(m_project->holdAt(i)) / fps, 'f', 6) << "\n";
    }
    // The concat demuxer ignores the duration of the last entry unless the
    // file is listed once more.
    if (count > 0)
        out << "file '" << escapeConcatPath(m_project->frameFile(count - 1)) << "'\n";
    return true;
}

bool Exporter::exportVideo(const QString &preset, bool preferHardware)
{
    if (busy())
        return false;
    if (m_project->frameCount() == 0) {
        setStatus(tr("Nenhum quadro para exportar."));
        return false;
    }
    m_preset = presets().contains(preset) ? preset : QStringLiteral("youtube");

    const QString exportDir = m_project->projectPath() + QStringLiteral("/export");
    QDir().mkpath(exportDir);
    m_listFile = exportDir + QStringLiteral("/.frames.txt");
    if (!writeConcatList(m_listFile)) {
        setStatus(tr("Falha ao preparar a lista de quadros."));
        return false;
    }
    m_output = exportDir + QStringLiteral("/%1_%2_%3.mp4")
                               .arg(m_project->projectName(), m_preset,
                                    QDateTime::currentDateTime().toString(QStringLiteral("yyyyMMdd-HHmmss")));
    m_totalSeconds = double(m_project->totalFrames()) / qMax(1, m_project->fps());
    m_cancelled = false;
    return start(preferHardware && vaapiAvailable());
}

bool Exporter::start(bool hardware)
{
    m_usingHardware = hardware;
    const QSize size = presetSize(m_preset);
    const QString fit = QStringLiteral("scale=%1:%2:force_original_aspect_ratio=decrease,"
                                       "pad=%1:%2:(ow-iw)/2:(oh-ih)/2:color=black")
                            .arg(size.width())
                            .arg(size.height());

    QStringList args{QStringLiteral("-y"), QStringLiteral("-hide_banner"),
                     QStringLiteral("-progress"), QStringLiteral("pipe:1"), QStringLiteral("-nostats")};
    if (hardware)
        args << QStringLiteral("-vaapi_device") << QString::fromLatin1(kRenderNode);
    args << QStringLiteral("-f") << QStringLiteral("concat") << QStringLiteral("-safe") << QStringLiteral("0")
         << QStringLiteral("-i") << m_listFile;
    if (hardware) {
        args << QStringLiteral("-vf") << fit + QStringLiteral(",format=nv12,hwupload")
             << QStringLiteral("-c:v") << QStringLiteral("h264_vaapi")
             << QStringLiteral("-qp") << QStringLiteral("20");
    } else {
        args << QStringLiteral("-vf") << fit + QStringLiteral(",format=yuv420p")
             << QStringLiteral("-c:v") << QStringLiteral("libx264")
             << QStringLiteral("-preset") << QStringLiteral("medium")
             << QStringLiteral("-crf") << QStringLiteral("18");
    }
    // The repeated last concat entry would otherwise add one extra frame.
    args << QStringLiteral("-fps_mode") << QStringLiteral("cfr")
         << QStringLiteral("-r") << QString::number(m_project->fps())
         << QStringLiteral("-frames:v") << QString::number(m_project->totalFrames())
         << QStringLiteral("-movflags") << QStringLiteral("+faststart")
         << m_output;

    m_progress = 0.0;
    emit progressChanged();
    setStatus(hardware ? tr("Exportando com a GPU (VAAPI)…") : tr("Exportando com a CPU (x264)…"));
    m_process.start(QStringLiteral("ffmpeg"), args);
    if (!m_process.waitForStarted(3000)) {
        setStatus(tr("FFmpeg não encontrado. Instale com: sudo apt install ffmpeg"));
        return false;
    }
    return true;
}

void Exporter::cancel()
{
    if (!busy())
        return;
    m_cancelled = true;
    m_process.terminate();
    if (!m_process.waitForFinished(2000))
        m_process.kill();
}

void Exporter::onFinished(int exitCode, QProcess::ExitStatus status)
{
    const bool ok = status == QProcess::NormalExit && exitCode == 0;
    if (!ok && !m_cancelled && m_usingHardware) {
        // VAAPI can fail on drivers without H.264 encode; retry on the CPU.
        QFile::remove(m_output);
        start(false);
        return;
    }
    QFile::remove(m_listFile);
    if (ok) {
        m_progress = 1.0;
        emit progressChanged();
        setStatus(tr("Vídeo exportado: %1").arg(QFileInfo(m_output).fileName()));
    } else {
        QFile::remove(m_output);
        setStatus(m_cancelled ? tr("Exportação cancelada.") : tr("Falha na exportação (FFmpeg código %1).").arg(exitCode));
    }
    emit finished(ok, ok ? m_output : QString());
}

void Exporter::setStatus(const QString &status)
{
    if (m_status == status)
        return;
    m_status = status;
    emit statusChanged();
}
