#pragma once

#include <QObject>
#include <QProcess>
#include <QStringList>

class Timeline;

// Renders the timeline to MP4:
//   1. each captured scene is pre-rendered to an intermediate clip (cached)
//   2. an MLT XML project is written (also openable in Shotcut/Kdenlive)
//   3. `melt` renders it, on the RX 580 encoder via VAAPI when available,
//      falling back to x264 on the CPU.
class TimelineRenderer : public QObject
{
    Q_OBJECT
    Q_PROPERTY(bool busy READ busy NOTIFY busyChanged)
    Q_PROPERTY(double progress READ progress NOTIFY progressChanged)
    Q_PROPERTY(QString status READ status NOTIFY statusChanged)
    Q_PROPERTY(QString lastOutput READ lastOutput NOTIFY finished)

public:
    explicit TimelineRenderer(Timeline *timeline, QObject *parent = nullptr);

    bool busy() const { return m_busy; }
    double progress() const { return m_progress; }
    QString status() const { return m_status; }
    QString lastOutput() const { return m_output; }

    Q_INVOKABLE bool render(bool preferHardware = true);
    Q_INVOKABLE void cancel();
    // Writes only the MLT project and returns its path (empty on failure).
    Q_INVOKABLE QString writeProject(const QString &path = QString());

signals:
    void busyChanged();
    void progressChanged();
    void statusChanged();
    void finished(bool ok, const QString &output);

private:
    struct SceneJob {
        QString dir;
        QString cache;
    };

    QString sceneCachePath(const QString &sceneDir) const;
    void nextScene();
    void startMelt(bool hardware);
    void onProcessFinished(int exitCode, QProcess::ExitStatus status);
    void finish(bool ok, const QString &message);
    void setStatus(const QString &status);
    void setBusy(bool busy);

    Timeline *m_timeline;
    QProcess m_process;
    QList<SceneJob> m_pending;
    int m_sceneCount = 0;
    enum class Phase { Idle, Scenes, Melt } m_phase = Phase::Idle;
    QString m_projectFile;
    QString m_output;
    QString m_status;
    double m_progress = 0.0;
    bool m_busy = false;
    bool m_hardware = false;
    bool m_preferHardware = true;
    bool m_cancelled = false;
};
