#include "speechtools.h"

#include <QCoreApplication>
#include <QCryptographicHash>
#include <QDir>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QRegularExpression>
#include <QStandardPaths>

namespace {

QString toolsDir()
{
    return qEnvironmentVariable("IA_SMS_HOME", QDir::homePath() + QStringLiteral("/IA-StopMotion")) + QStringLiteral("/ferramentas");
}

QString firstExisting(const QString &envVar, const QStringList &candidates, bool executable)
{
    const QString env = qEnvironmentVariable(envVar.toLatin1().constData());
    const QStringList list = env.isEmpty() ? candidates : QStringList{env};
    for (const QString &c : list) {
        const QFileInfo fi(c);
        if (fi.exists() && (!executable || fi.isExecutable()))
            return fi.absoluteFilePath();
    }
    return {};
}

double srtTime(const QString &t)
{
    // 00:01:02,345
    static const QRegularExpression re(QStringLiteral("(\\d+):(\\d+):(\\d+)[,.](\\d+)"));
    const auto m = re.match(t);
    if (!m.hasMatch())
        return 0;
    return m.captured(1).toInt() * 3600 + m.captured(2).toInt() * 60 + m.captured(3).toInt() + m.captured(4).toInt() / 1000.0;
}

} // namespace

SpeechTools::SpeechTools(QObject *parent)
    : QObject(parent)
    , m_tmpBase(QDir::tempPath() + QStringLiteral("/ia-sms-fala-%1").arg(QCoreApplication::applicationPid()))
{
    QDir().mkpath(m_tmpBase);
    connect(&m_proc, &QProcess::stateChanged, this, &SpeechTools::busyChanged);
    connect(&m_proc, &QProcess::finished, this, &SpeechTools::onFinished);
}

SpeechTools::~SpeechTools()
{
    cancel();
    QDir(m_tmpBase).removeRecursively();
}

QString SpeechTools::whisperPath()
{
    const QString found = firstExisting(QStringLiteral("IA_SMS_WHISPER"),
                                        {toolsDir() + QStringLiteral("/whisper/whisper-cli")}, true);
    return found.isEmpty() && qEnvironmentVariableIsEmpty("IA_SMS_WHISPER")
               ? QStandardPaths::findExecutable(QStringLiteral("whisper-cli")) : found;
}

QString SpeechTools::whisperModel()
{
    const QString dir = toolsDir() + QStringLiteral("/whisper/");
    // Bigger models transcribe Portuguese better; use the best one installed.
    return firstExisting(QStringLiteral("IA_SMS_WHISPER_MODEL"),
                         {dir + QStringLiteral("ggml-medium.bin"), dir + QStringLiteral("ggml-small.bin"),
                          dir + QStringLiteral("ggml-base.bin"), dir + QStringLiteral("ggml-tiny.bin")}, false);
}

QString SpeechTools::piperPath()
{
    const QString found = firstExisting(QStringLiteral("IA_SMS_PIPER"), {toolsDir() + QStringLiteral("/piper/piper")}, true);
    return found.isEmpty() && qEnvironmentVariableIsEmpty("IA_SMS_PIPER")
               ? QStandardPaths::findExecutable(QStringLiteral("piper")) : found;
}

QString SpeechTools::piperVoice()
{
    const QString env = qEnvironmentVariable("IA_SMS_PIPER_VOICE");
    if (!env.isEmpty())
        return QFileInfo::exists(env) ? env : QString();
    const QDir dir(toolsDir() + QStringLiteral("/piper/vozes"));
    const QStringList voices = dir.entryList({QStringLiteral("*.onnx")}, QDir::Files, QDir::Name);
    return voices.isEmpty() ? QString() : dir.absoluteFilePath(voices.first());
}

QVariantList SpeechTools::parseSrt(const QString &srt)
{
    QVariantList segments;
    const QStringList blocks = QString(srt).replace(QStringLiteral("\r\n"), QStringLiteral("\n"))
                                   .split(QRegularExpression(QStringLiteral("\n\\s*\n")), Qt::SkipEmptyParts);
    for (const QString &block : blocks) {
        QStringList lines = block.trimmed().split(QLatin1Char('\n'));
        int timeLine = -1;
        for (int i = 0; i < lines.size(); ++i) {
            if (lines.at(i).contains(QLatin1String("-->"))) { timeLine = i; break; }
        }
        if (timeLine < 0)
            continue;
        const QStringList times = lines.at(timeLine).split(QStringLiteral("-->"));
        const QString text = lines.mid(timeLine + 1).join(QLatin1Char('\n')).trimmed();
        if (times.size() != 2 || text.isEmpty())
            continue;
        segments.append(QVariantMap{{QStringLiteral("start"), srtTime(times.at(0))},
                                    {QStringLiteral("end"), srtTime(times.at(1))},
                                    {QStringLiteral("text"), text}});
    }
    return segments;
}

void SpeechTools::setLanguage(const QString &lang)
{
    if (lang == m_language || lang.isEmpty())
        return;
    m_language = lang;
    emit languageChanged();
}

void SpeechTools::setStatus(const QString &s)
{
    if (s == m_status)
        return;
    m_status = s;
    emit statusChanged();
}

QString SpeechTools::cacheFile(const QString &audio) const
{
    // Next to the audio, keyed by size, mtime, model and language.
    const QFileInfo fi(audio);
    const QByteArray key = QStringLiteral("%1|%2|%3|%4").arg(fi.size()).arg(fi.lastModified().toMSecsSinceEpoch())
                               .arg(QFileInfo(whisperModel()).fileName(), m_language).toUtf8();
    return audio + QStringLiteral(".legendas-%1.json")
                       .arg(QString::fromLatin1(QCryptographicHash::hash(key, QCryptographicHash::Sha1).toHex().left(10)));
}

bool SpeechTools::transcribe(const QStringList &audioFiles)
{
    if (busy())
        return false;
    if (!whisperAvailable()) {
        setStatus(tr("Legendas automáticas não instaladas: rode scripts/instalar-voz.sh"));
        emit failed(m_status);
        return false;
    }
    m_results.clear();
    m_queue.clear();
    for (const QString &f : audioFiles) {
        if (m_queue.contains(f) || !QFileInfo::exists(f))
            continue;
        // Reuse cached transcripts.
        QFile cache(cacheFile(f));
        if (cache.open(QIODevice::ReadOnly)) {
            m_results.insert(f, QJsonDocument::fromJson(cache.readAll()).array().toVariantList());
            continue;
        }
        m_queue << f;
    }
    m_total = m_queue.size();
    emit busyChanged();
    next();
    return true;
}

void SpeechTools::next()
{
    if (m_queue.isEmpty()) {
        m_job = Job::None;
        setStatus(tr("Legendas prontas."));
        emit busyChanged();
        emit transcriptionFinished(m_results);
        return;
    }
    m_current = m_queue.first();
    setStatus(tr("Transcrevendo %1 de %2: %3…").arg(m_total - m_queue.size() + 1).arg(m_total).arg(QFileInfo(m_current).fileName()));
    // whisper.cpp wants 16 kHz mono WAV.
    m_job = Job::Convert;
    m_proc.start(QStringLiteral("ffmpeg"), {QStringLiteral("-v"), QStringLiteral("error"), QStringLiteral("-y"),
                                            QStringLiteral("-i"), m_current, QStringLiteral("-ar"), QStringLiteral("16000"),
                                            QStringLiteral("-ac"), QStringLiteral("1"), QStringLiteral("-c:a"),
                                            QStringLiteral("pcm_s16le"), m_tmpBase + QStringLiteral("/entrada.wav")});
}

bool SpeechTools::narrate(const QString &text, const QString &outFile)
{
    if (busy() || text.trimmed().isEmpty())
        return false;
    if (!piperAvailable()) {
        setStatus(tr("Narração não instalada: rode scripts/instalar-voz.sh"));
        emit failed(m_status);
        return false;
    }
    QDir().mkpath(QFileInfo(outFile).absolutePath());
    m_narrationOut = outFile;
    m_job = Job::Piper;
    setStatus(tr("Gerando narração…"));
    m_proc.start(piperPath(), {QStringLiteral("--model"), piperVoice(), QStringLiteral("--output_file"), outFile});
    m_proc.write(text.toUtf8());
    m_proc.closeWriteChannel();
    return true;
}

void SpeechTools::cancel()
{
    m_queue.clear();
    if (m_proc.state() != QProcess::NotRunning) {
        m_job = Job::None;
        m_proc.kill();
        m_proc.waitForFinished(2000);
    }
}

void SpeechTools::onFinished(int code, QProcess::ExitStatus st)
{
    const bool ok = st == QProcess::NormalExit && code == 0;
    const QString err = QString::fromUtf8(m_proc.readAllStandardError()).trimmed().right(240);
    switch (m_job) {
    case Job::None:
        return;
    case Job::Piper:
        m_job = Job::None;
        if (ok && QFileInfo(m_narrationOut).size() > 44) {
            setStatus(tr("Narração pronta."));
            emit narrationReady(m_narrationOut);
        } else {
            setStatus(tr("Piper falhou: %1").arg(err));
            emit failed(m_status);
        }
        emit busyChanged();
        return;
    case Job::Convert:
        if (!ok) {
            setStatus(tr("Não foi possível ler %1").arg(QFileInfo(m_current).fileName()));
            m_queue.removeFirst();
            next();
            return;
        }
        m_job = Job::Whisper;
        QFile::remove(m_tmpBase + QStringLiteral("/saida.srt"));
        m_proc.start(whisperPath(), {QStringLiteral("-m"), whisperModel(), QStringLiteral("-l"), m_language,
                                     QStringLiteral("-osrt"), QStringLiteral("-of"), m_tmpBase + QStringLiteral("/saida"),
                                     QStringLiteral("-f"), m_tmpBase + QStringLiteral("/entrada.wav")});
        return;
    case Job::Whisper: {
        QFile srt(m_tmpBase + QStringLiteral("/saida.srt"));
        if (ok && srt.open(QIODevice::ReadOnly)) {
            const QVariantList segments = parseSrt(QString::fromUtf8(srt.readAll()));
            m_results.insert(m_current, segments);
            QFile cache(cacheFile(m_current));
            if (cache.open(QIODevice::WriteOnly))
                cache.write(QJsonDocument(QJsonArray::fromVariantList(segments)).toJson());
        } else {
            setStatus(tr("whisper.cpp falhou: %1").arg(err));
            emit failed(m_status);
        }
        m_queue.removeFirst();
        next();
        return;
    }
    }
}
