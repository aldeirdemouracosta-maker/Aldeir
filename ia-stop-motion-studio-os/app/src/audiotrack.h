#pragma once

#include <QObject>
#include <QProcess>
#include <QVariantList>

class ProjectManager;

// Analyses the project's reference soundtrack for the capture dope sheet:
//   - loudness per animation frame (waveform)
//   - mouth shape per frame from Rhubarb Lip Sync (A–H, X), which tells the
//     animator which mouth to put on the puppet for every photo.
// Rhubarb runs with its language-independent "phonetic" recognizer, so it
// also works for Portuguese dialogue.
class AudioTrack : public QObject
{
    Q_OBJECT
    Q_PROPERTY(QVariantList waveform READ waveform NOTIFY waveformChanged)
    Q_PROPERTY(int lengthFrames READ lengthFrames NOTIFY waveformChanged)
    Q_PROPERTY(QVariantList mouths READ mouths NOTIFY mouthsChanged)
    Q_PROPERTY(bool lipSyncAvailable READ lipSyncAvailable CONSTANT)
    Q_PROPERTY(bool busy READ busy NOTIFY busyChanged)
    Q_PROPERTY(QString status READ status NOTIFY statusChanged)

public:
    explicit AudioTrack(ProjectManager *project, QObject *parent = nullptr);

    QVariantList waveform() const { return m_waveform; }
    int lengthFrames() const { return int(m_waveform.size()); }
    QVariantList mouths() const { return m_mouths; }
    bool lipSyncAvailable() const { return !rhubarbPath().isEmpty(); }
    bool busy() const { return m_waveProc.state() != QProcess::NotRunning || m_lipProc.state() != QProcess::NotRunning; }
    QString status() const { return m_status; }

    // Mouth shape for a project frame ("" when unknown / outside the audio).
    Q_INVOKABLE QString mouthAt(int frame) const;
    Q_INVOKABLE static QString mouthDescription(const QString &shape);
    Q_INVOKABLE void analyze();
    Q_INVOKABLE bool runLipSync();

    static QString rhubarbPath();

signals:
    void waveformChanged();
    void mouthsChanged();
    void busyChanged();
    void statusChanged();

private:
    QString cueFile() const; // cached Rhubarb result next to the audio
    void loadCues();
    void setStatus(const QString &status);

    ProjectManager *m_project;
    QProcess m_waveProc;
    QProcess m_lipProc;
    QByteArray m_pcm;
    QVariantList m_waveform;
    QVariantList m_mouths;
    QList<QPair<double, QString>> m_cues; // start seconds → shape
    QString m_status;
};
