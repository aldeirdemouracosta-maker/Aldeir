#pragma once

#include <QColor>
#include <QFutureWatcher>
#include <QObject>
#include <QUrl>
#include <QVariantList>

#include <functional>

class ProjectManager;

// "IA Local" tools applied to the photos of the current project:
//   - rig/wire removal with a painted mask (clean plate or fill)
//   - chroma key background replacement
//   - AI upscale with Real-ESRGAN (ncnn + Vulkan, runs on the RX 580)
// Work runs in a worker thread; every edited photo keeps its original in
// <projeto>/originais/ and can be restored.
class FrameTools : public QObject
{
    Q_OBJECT
    Q_PROPERTY(bool busy READ busy NOTIFY busyChanged)
    Q_PROPERTY(double progress READ progress NOTIFY progressChanged)
    Q_PROPERTY(QString status READ status NOTIFY statusChanged)
    Q_PROPERTY(QUrl previewUrl READ previewUrl NOTIFY previewChanged)
    Q_PROPERTY(bool upscalerAvailable READ upscalerAvailable CONSTANT)

public:
    explicit FrameTools(ProjectManager *project, QObject *parent = nullptr);
    ~FrameTools() override;

    bool busy() const { return m_watcher.isRunning(); }
    double progress() const { return m_progress; }
    QString status() const { return m_status; }
    QUrl previewUrl() const { return m_previewUrl; }
    bool upscalerAvailable() const { return !upscalerPath().isEmpty(); }

    static QString upscalerPath();

    Q_INVOKABLE bool previewCleanup(int index, const QString &maskPath, bool usePlate, int feather);
    Q_INVOKABLE bool previewChroma(int index, const QColor &key, double tolerance, double softness, bool spill,
                                   const QUrl &background);
    Q_INVOKABLE void clearPreview();

    Q_INVOKABLE bool applyCleanup(const QVariantList &indices, const QString &maskPath, bool usePlate, int feather);
    Q_INVOKABLE bool applyChroma(const QVariantList &indices, const QColor &key, double tolerance, double softness,
                                 bool spill, const QUrl &background);
    Q_INVOKABLE bool upscale(const QVariantList &indices, int factor);
    Q_INVOKABLE int restore(const QVariantList &indices);

    // Colour of a photo at normalised coordinates (eyedropper).
    Q_INVOKABLE QColor colorAt(int index, double nx, double ny) const;

signals:
    void busyChanged();
    void progressChanged();
    void statusChanged();
    void previewChanged();
    void finished(bool ok, const QString &message);

private:
    using Operation = std::function<QImage(const QImage &)>;
    bool runBatch(const QVariantList &indices, const QString &label, const Operation &op);
    bool runPreview(int index, const Operation &op);
    void setStatus(const QString &status);
    void setProgress(double progress);

    ProjectManager *m_project;
    QFutureWatcher<QString> m_watcher; // result: status message ("" = ok)
    QList<int> m_touched;
    QUrl m_previewUrl;
    int m_previewRev = 0;
    QString m_status;
    double m_progress = 0.0;
};
