#pragma once

#include <QHash>
#include <QSize>
#include <QObject>
#include <QUrl>
#include <QVariantList>

#include "scene.h"

class ProjectManager;

// Film timeline stored next to the current project (<projeto>/timeline.json).
// Three kinds of tracks, like a simplified Clipchamp:
//   video  – captured scenes, video files and still images, played in order,
//            with an optional dissolve into each clip
//   titles – text overlays placed at any time
//   audio  – music, narration and effects placed at any time
// All positions and lengths are in timeline frames (at `fps`).
class Timeline : public QObject
{
    Q_OBJECT
    Q_PROPERTY(int fps READ fps WRITE setFps NOTIFY changed)
    Q_PROPERTY(QString format READ format WRITE setFormat NOTIFY changed)
    Q_PROPERTY(QSize frameSize READ frameSize NOTIFY changed)
    Q_PROPERTY(QVariantList videoClips READ videoClips NOTIFY changed)
    Q_PROPERTY(QVariantList titles READ titles NOTIFY changed)
    Q_PROPERTY(QVariantList audioClips READ audioClips NOTIFY changed)
    Q_PROPERTY(int duration READ duration NOTIFY changed)
    Q_PROPERTY(QVariantList availableScenes READ availableScenes NOTIFY scenesChanged)

public:
    struct VideoClip {
        QString id;
        QString type; // scene | video | image
        QString source;
        QString name;
        int in = 0;
        int out = 0; // exclusive
        int sourceLength = 0; // 0 = unlimited (still image)
        int transition = 0; // dissolve frames into this clip
        double volume = 0.0; // dB, for video files with sound
        int start = 0; // computed
    };
    struct Title {
        QString id;
        QString text;
        int start = 0;
        int length = 72;
        QString position = QStringLiteral("bottom"); // top | center | bottom
        int size = 8; // percent of frame height
        QString color = QStringLiteral("#FFFFFF");
        bool box = true; // dark band behind the text
        QString image; // rendered PNG (computed)
    };
    struct AudioClip {
        QString id;
        QString source;
        QString name;
        int start = 0;
        int in = 0;
        int out = 0;
        int sourceLength = 0;
        double volume = 0.0;
    };

    explicit Timeline(ProjectManager *project, QObject *parent = nullptr);

    int fps() const { return m_fps; }
    void setFps(int fps);
    QString format() const { return m_format; }
    void setFormat(const QString &format);
    QSize frameSize() const;
    QVariantList videoClips() const;
    QVariantList titles() const;
    QVariantList audioClips() const;
    int duration() const;
    QVariantList availableScenes() const;

    const QList<VideoClip> &videoList() const { return m_video; }
    const QList<Title> &titleList() const { return m_titles; }
    const QList<AudioClip> &audioList() const { return m_audio; }
    QString filePath() const;
    QString workDir() const; // <projeto>/export

    Q_INVOKABLE bool addScene(const QString &projectDir);
    Q_INVOKABLE int addMedia(const QList<QUrl> &urls, int atFrame = -1);
    Q_INVOKABLE void addTitle(const QString &text, int atFrame);
    Q_INVOKABLE void moveClip(int index, int delta);
    Q_INVOKABLE void removeVideo(int index);
    Q_INVOKABLE void removeTitle(int index);
    Q_INVOKABLE void removeAudio(int index);
    Q_INVOKABLE bool splitAt(int frame);
    Q_INVOKABLE void setVideoProperty(int index, const QString &key, const QVariant &value);
    Q_INVOKABLE void setTitleProperty(int index, const QString &key, const QVariant &value);
    Q_INVOKABLE void setAudioProperty(int index, const QString &key, const QVariant &value);
    // What the preview monitor should show at a timeline frame: a list of
    // layers {kind, url, seconds, opacity, clip}, bottom first.
    Q_INVOKABLE QVariantList layersAt(int frame);
    Q_INVOKABLE QString timecode(int frame) const;
    Q_INVOKABLE void reload();

signals:
    void changed();
    void scenesChanged();
    void errorOccurred(const QString &message);

private:
    void load();
    void save();
    void relayout();
    void touch(); // relayout + save + changed
    void renderTitleImage(Title &title);
    int probeFrames(const QString &file) const;
    const Scene &scene(const QString &dir);
    static QString newId();

    ProjectManager *m_project;
    int m_fps = 24;
    QString m_format = QStringLiteral("youtube");
    QList<VideoClip> m_video;
    QList<Title> m_titles;
    QList<AudioClip> m_audio;
    QHash<QString, Scene> m_sceneCache;
};
