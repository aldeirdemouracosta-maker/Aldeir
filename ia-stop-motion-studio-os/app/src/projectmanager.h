#pragma once

#include <QObject>
#include <QImage>
#include <QPointer>
#include <QStringList>
#include <QUrl>
#include <QVariantList>

class QImageCapture;

// Owns the current stop-motion project on disk:
//   <base>/Projetos/<name>/project.json
//   <base>/Projetos/<name>/frames/frame_000001.png
// Every captured frame is written atomically (temp file + fsync + rename) so a
// crash during a long capture session never loses or corrupts earlier frames.
class ProjectManager : public QObject
{
    Q_OBJECT
    Q_PROPERTY(QString projectName READ projectName NOTIFY projectChanged)
    Q_PROPERTY(QString projectPath READ projectPath NOTIFY projectChanged)
    Q_PROPERTY(int fps READ fps WRITE setFps NOTIFY fpsChanged)
    Q_PROPERTY(int frameCount READ frameCount NOTIFY framesChanged)
    Q_PROPERTY(QVariantList frames READ frames NOTIFY framesChanged)
    Q_PROPERTY(int totalFrames READ totalFrames NOTIFY framesChanged)
    Q_PROPERTY(QString durationText READ durationText NOTIFY framesChanged)
    Q_PROPERTY(QString resolutionText READ resolutionText NOTIFY framesChanged)
    Q_PROPERTY(QString baseDir READ baseDir CONSTANT)
    Q_PROPERTY(QVariantList recentProjects READ recentProjects NOTIFY recentProjectsChanged)
    Q_PROPERTY(QString lastError READ lastError NOTIFY errorOccurred)
    Q_PROPERTY(QString audioFile READ audioFile NOTIFY audioChanged)
    Q_PROPERTY(QString audioName READ audioName NOTIFY audioChanged)
    Q_PROPERTY(int audioOffset READ audioOffset WRITE setAudioOffset NOTIFY audioChanged)
    Q_PROPERTY(bool deflicker READ deflicker WRITE setDeflicker NOTIFY deflickerChanged)

public:
    explicit ProjectManager(QObject *parent = nullptr);

    QString projectName() const { return m_name; }
    QString projectPath() const { return m_path; }
    int fps() const { return m_fps; }
    void setFps(int fps);
    int frameCount() const { return m_frames.size(); }
    QVariantList frames() const;
    int totalFrames() const;
    QString durationText() const;
    QString resolutionText() const;
    QString baseDir() const { return m_baseDir; }
    QVariantList recentProjects() const;
    QString lastError() const { return m_lastError; }
    QString audioFile() const;
    QString audioName() const;
    int audioOffset() const { return m_audioOffset; }
    void setAudioOffset(int frames);
    bool deflicker() const { return m_deflicker; }
    void setDeflicker(bool on);

    Q_INVOKABLE bool newProject(const QString &name);
    Q_INVOKABLE bool openProject(const QString &path);
    Q_INVOKABLE void attachImageCapture(QObject *imageCapture);
    Q_INVOKABLE bool addFrame(const QImage &image);
    Q_INVOKABLE int importImages(const QList<QUrl> &urls);
    Q_INVOKABLE bool deleteFrame(int index);
    Q_INVOKABLE bool deleteLastFrame();
    Q_INVOKABLE void setHold(int index, int hold);
    Q_INVOKABLE QUrl frameUrl(int index) const;
    Q_INVOKABLE QString frameFile(int index) const;
    Q_INVOKABLE int holdAt(int index) const;
    // Reference soundtrack (dialogue/music) the animation is timed against.
    // The file is copied into <projeto>/audio/.
    Q_INVOKABLE bool setAudio(const QUrl &url);
    Q_INVOKABLE void removeAudio();

signals:
    void projectChanged();
    void framesChanged();
    void fpsChanged();
    void recentProjectsChanged();
    void frameSaved(int index);
    void audioChanged();
    void deflickerChanged();
    void errorOccurred(const QString &message);

private:
    struct Frame {
        QString file; // relative to project dir
        int hold = 1; // how many video frames this photo stays on screen
    };

    bool saveManifest();
    bool loadManifest();
    QString nextFrameFileName() const;
    void fail(const QString &message);

    QString m_baseDir;
    QString m_name;
    QString m_path;
    int m_fps = 12;
    int m_nextIndex = 1;
    QSize m_resolution;
    QList<Frame> m_frames;
    QString m_audio; // relative to project dir
    int m_audioOffset = 0; // project frame where the audio starts
    bool m_deflicker = false;
    QString m_lastError;
    QPointer<QImageCapture> m_capture;
};
