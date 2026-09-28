#include "audiotrack.h"
#include "projectmanager.h"

#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QHash>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QStandardPaths>

#include <cmath>

namespace {

constexpr int kSampleRate = 8000; // plenty for a per-frame loudness envelope

} // namespace

AudioTrack::AudioTrack(ProjectManager *project, QObject *parent)
    : QObject(parent)
    , m_project(project)
{
    connect(project, &ProjectManager::audioChanged, this, &AudioTrack::analyze);
    connect(project, &ProjectManager::projectChanged, this, &AudioTrack::analyze);
    connect(project, &ProjectManager::fpsChanged, this, &AudioTrack::analyze);

    connect(&m_waveProc, &QProcess::readyReadStandardOutput, this, [this] { m_pcm += m_waveProc.readAllStandardOutput(); });
    connect(&m_waveProc, &QProcess::stateChanged, this, &AudioTrack::busyChanged);
    connect(&m_waveProc, &QProcess::finished, this, [this](int code, QProcess::ExitStatus st) {
        m_waveform.clear();
        if (st == QProcess::NormalExit && code == 0) {
            const auto *samples = reinterpret_cast<const qint16 *>(m_pcm.constData());
            const qsizetype count = m_pcm.size() / 2;
            const double perFrame = double(kSampleRate) / qMax(1, m_project->fps());
            const int frames = int(std::ceil(count / perFrame));
            QList<double> rms(frames, 0.0);
            double peak = 1e-9;
            for (int f = 0; f < frames; ++f) {
                const qsizetype a = qsizetype(f * perFrame), b = qMin(count, qsizetype((f + 1) * perFrame));
                double sum = 0;
                for (qsizetype i = a; i < b; ++i)
                    sum += double(samples[i]) * samples[i];
                rms[f] = b > a ? std::sqrt(sum / double(b - a)) : 0.0;
                peak = qMax(peak, rms[f]);
            }
            // Offset: the audio starts at project frame audioOffset.
            for (int i = 0; i < m_project->audioOffset(); ++i)
                m_waveform.append(0.0);
            for (double v : rms)
                m_waveform.append(v / peak);
            setStatus(QString());
        } else {
            setStatus(tr("Não foi possível ler o áudio (FFmpeg)."));
        }
        m_pcm.clear();
        emit waveformChanged();
        loadCues();
    });

    connect(&m_lipProc, &QProcess::stateChanged, this, &AudioTrack::busyChanged);
    connect(&m_lipProc, &QProcess::finished, this, [this](int code, QProcess::ExitStatus st) {
        if (st == QProcess::NormalExit && code == 0) {
            setStatus(tr("Sincronia labial pronta."));
            loadCues();
        } else {
            QFile::remove(cueFile());
            setStatus(tr("Rhubarb falhou: %1").arg(QString::fromUtf8(m_lipProc.readAllStandardError()).trimmed().right(200)));
        }
    });

    analyze();
}

QString AudioTrack::rhubarbPath()
{
    const QString env = qEnvironmentVariable("IA_SMS_RHUBARB");
    if (!env.isEmpty() && QFileInfo(env).isExecutable())
        return env;
    const QString found = QStandardPaths::findExecutable(QStringLiteral("rhubarb"));
    if (!found.isEmpty())
        return found;
    const QString home = qEnvironmentVariable("IA_SMS_HOME", QDir::homePath() + QStringLiteral("/IA-StopMotion"));
    const QString bundled = home + QStringLiteral("/ferramentas/rhubarb/rhubarb");
    return QFileInfo(bundled).isExecutable() ? bundled : QString();
}

QString AudioTrack::cueFile() const
{
    const QString audio = m_project->audioFile();
    return audio.isEmpty() ? QString() : audio + QStringLiteral(".boca.json");
}

void AudioTrack::analyze()
{
    if (m_waveProc.state() != QProcess::NotRunning) {
        m_waveProc.kill();
        m_waveProc.waitForFinished(1000);
    }
    m_pcm.clear();
    const QString audio = m_project->audioFile();
    if (audio.isEmpty()) {
        m_waveform.clear();
        m_cues.clear();
        m_mouths.clear();
        emit waveformChanged();
        emit mouthsChanged();
        return;
    }
    setStatus(tr("Analisando áudio…"));
    m_waveProc.start(QStringLiteral("ffmpeg"), {QStringLiteral("-v"), QStringLiteral("error"), QStringLiteral("-i"), audio,
                                                 QStringLiteral("-ac"), QStringLiteral("1"), QStringLiteral("-ar"),
                                                 QString::number(kSampleRate), QStringLiteral("-f"), QStringLiteral("s16le"),
                                                 QStringLiteral("-")});
}

bool AudioTrack::runLipSync()
{
    const QString rhubarb = rhubarbPath();
    const QString audio = m_project->audioFile();
    if (rhubarb.isEmpty() || audio.isEmpty() || m_lipProc.state() != QProcess::NotRunning)
        return false;
    // Rhubarb reads WAV/OGG; convert anything else to a temporary WAV first.
    QString input = audio;
    const QString suffix = QFileInfo(audio).suffix().toLower();
    if (suffix != QLatin1String("wav") && suffix != QLatin1String("ogg")) {
        input = audio + QStringLiteral(".rhubarb.wav");
        if (QProcess::execute(QStringLiteral("ffmpeg"), {QStringLiteral("-v"), QStringLiteral("error"), QStringLiteral("-y"),
                                                         QStringLiteral("-i"), audio, QStringLiteral("-ac"), QStringLiteral("1"),
                                                         input}) != 0) {
            setStatus(tr("Falha ao converter o áudio para WAV."));
            return false;
        }
    }
    setStatus(tr("Calculando sincronia labial (Rhubarb)…"));
    m_lipProc.start(rhubarb, {QStringLiteral("-r"), QStringLiteral("phonetic"), QStringLiteral("-f"), QStringLiteral("json"),
                              QStringLiteral("-q"), QStringLiteral("-o"), cueFile(), input});
    return true;
}

void AudioTrack::loadCues()
{
    m_cues.clear();
    m_mouths.clear();
    QFile file(cueFile());
    if (!cueFile().isEmpty() && file.open(QIODevice::ReadOnly)) {
        const QJsonArray cues = QJsonDocument::fromJson(file.readAll()).object().value(QStringLiteral("mouthCues")).toArray();
        for (const QJsonValue &v : cues) {
            const QJsonObject c = v.toObject();
            m_cues.append({c.value(QStringLiteral("start")).toDouble(), c.value(QStringLiteral("value")).toString()});
        }
    }
    if (!m_cues.isEmpty()) {
        for (int f = 0; f < m_waveform.size(); ++f)
            m_mouths.append(mouthAt(f));
    }
    emit mouthsChanged();
}

QString AudioTrack::mouthAt(int frame) const
{
    if (m_cues.isEmpty())
        return {};
    // Sample the middle of the frame, relative to where the audio starts.
    const double t = (frame - m_project->audioOffset() + 0.5) / qMax(1, m_project->fps());
    if (t < 0)
        return {};
    QString shape = m_cues.first().second;
    for (const auto &cue : m_cues) {
        if (cue.first > t)
            break;
        shape = cue.second;
    }
    return shape;
}

QString AudioTrack::mouthDescription(const QString &shape)
{
    static const QHash<QString, QString> names{
        {QStringLiteral("A"), QStringLiteral("fechada — M, B, P")},
        {QStringLiteral("B"), QStringLiteral("dentes quase juntos — K, S, T")},
        {QStringLiteral("C"), QStringLiteral("aberta — É, Ê")},
        {QStringLiteral("D"), QStringLiteral("bem aberta — A")},
        {QStringLiteral("E"), QStringLiteral("arredondada — Ó, Ô")},
        {QStringLiteral("F"), QStringLiteral("bico — U, W")},
        {QStringLiteral("G"), QStringLiteral("dentes no lábio — F, V")},
        {QStringLiteral("H"), QStringLiteral("língua — L")},
        {QStringLiteral("X"), QStringLiteral("repouso")},
    };
    return names.value(shape);
}

void AudioTrack::setStatus(const QString &status)
{
    if (m_status == status)
        return;
    m_status = status;
    emit statusChanged();
}
