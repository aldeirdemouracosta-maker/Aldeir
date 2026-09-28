#pragma once

#include <QObject>
#include <QProcess>
#include <QStringList>

class ProjectManager;

// Turns the frame sequence (with per-frame holds) into an MP4 using FFmpeg.
// Prefers the GPU's hardware encoder through VAAPI (VCE on the RX 580) and
// falls back to libx264 on the CPU when VAAPI is missing or fails.
class Exporter : public QObject
{
    Q_OBJECT
    Q_PROPERTY(bool busy READ busy NOTIFY busyChanged)
    Q_PROPERTY(double progress READ progress NOTIFY progressChanged)
    Q_PROPERTY(QString status READ status NOTIFY statusChanged)
    Q_PROPERTY(QString lastOutput READ lastOutput NOTIFY finished)
    Q_PROPERTY(bool vaapiAvailable READ vaapiAvailable CONSTANT)
    Q_PROPERTY(QStringList presets READ presets CONSTANT)

public:
    explicit Exporter(ProjectManager *project, QObject *parent = nullptr);

    bool busy() const { return m_process.state() != QProcess::NotRunning; }
    double progress() const { return m_progress; }
    QString status() const { return m_status; }
    QString lastOutput() const { return m_output; }
    bool vaapiAvailable() const;
    QStringList presets() const;

    // preset: "youtube" (16:9 1080p), "vertical" (9:16 Reels/TikTok),
    //         "quadrado" (1:1), "4k" (16:9 2160p)
    Q_INVOKABLE bool exportVideo(const QString &preset, bool preferHardware = true);
    Q_INVOKABLE void cancel();

signals:
    void busyChanged();
    void progressChanged();
    void statusChanged();
    void finished(bool ok, const QString &output);

private:
    bool start(bool hardware);
    bool writeConcatList(const QString &path) const;
    void setStatus(const QString &status);
    void onFinished(int exitCode, QProcess::ExitStatus status);

    ProjectManager *m_project;
    QProcess m_process;
    QString m_preset;
    QString m_output;
    QString m_listFile;
    QString m_status;
    double m_progress = 0.0;
    double m_totalSeconds = 0.0;
    bool m_usingHardware = false;
    bool m_cancelled = false;
};
