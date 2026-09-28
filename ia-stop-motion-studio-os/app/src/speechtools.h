#pragma once

#include <QHash>
#include <QObject>
#include <QProcess>
#include <QStringList>
#include <QVariantList>

// Local speech tools:
//   - subtitles: whisper.cpp (whisper-cli) transcribes dialogue/narration to
//     timed segments (Portuguese by default); results are cached per file
//   - narration: Piper text-to-speech writes a WAV from typed text
// Installed by scripts/instalar-voz.sh into <base>/ferramentas.
class SpeechTools : public QObject
{
    Q_OBJECT
    Q_PROPERTY(bool whisperAvailable READ whisperAvailable CONSTANT)
    Q_PROPERTY(bool piperAvailable READ piperAvailable CONSTANT)
    Q_PROPERTY(bool busy READ busy NOTIFY busyChanged)
    Q_PROPERTY(QString status READ status NOTIFY statusChanged)
    Q_PROPERTY(QString language READ language WRITE setLanguage NOTIFY languageChanged)

public:
    explicit SpeechTools(QObject *parent = nullptr);
    ~SpeechTools() override;

    static QString whisperPath();
    static QString whisperModel();
    static QString piperPath();
    static QString piperVoice();
    // Parses SubRip text into [{start, end, text}] (seconds).
    static QVariantList parseSrt(const QString &srt);

    bool whisperAvailable() const { return !whisperPath().isEmpty() && !whisperModel().isEmpty(); }
    bool piperAvailable() const { return !piperPath().isEmpty() && !piperVoice().isEmpty(); }
    bool busy() const { return m_proc.state() != QProcess::NotRunning || !m_queue.isEmpty(); }
    QString status() const { return m_status; }
    QString language() const { return m_language; }
    void setLanguage(const QString &lang);

    // Transcribes the files one after another; emits transcriptionFinished
    // with {file: segments}.
    Q_INVOKABLE bool transcribe(const QStringList &audioFiles);
    // Speaks `text` into `outFile` (WAV); emits narrationReady.
    Q_INVOKABLE bool narrate(const QString &text, const QString &outFile);
    Q_INVOKABLE void cancel();

signals:
    void busyChanged();
    void statusChanged();
    void languageChanged();
    void transcriptionFinished(const QVariantMap &results);
    void narrationReady(const QString &file);
    void failed(const QString &message);

private:
    enum class Job { None, Convert, Whisper, Piper };
    void next();
    void onFinished(int code, QProcess::ExitStatus status);
    QString cacheFile(const QString &audio) const;
    void setStatus(const QString &s);

    QProcess m_proc;
    Job m_job = Job::None;
    QStringList m_queue;
    QString m_current;
    QString m_tmpBase;
    QString m_narrationOut;
    QVariantMap m_results;
    QString m_status;
    QString m_language = QStringLiteral("pt");
    int m_total = 0;
};
