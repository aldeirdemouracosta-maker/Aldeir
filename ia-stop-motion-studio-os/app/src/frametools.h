#pragma once

#include <QColor>
#include <QFutureWatcher>
#include <QObject>
#include <QProcess>
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
    Q_PROPERTY(bool aiBackgroundAvailable READ aiBackgroundAvailable CONSTANT)
    Q_PROPERTY(bool aiFillAvailable READ aiFillAvailable CONSTANT)

public:
    explicit FrameTools(ProjectManager *project, QObject *parent = nullptr);
    ~FrameTools() override;

    bool busy() const { return m_watcher.isRunning() || m_ai.state() != QProcess::NotRunning; }
    double progress() const { return m_progress; }
    QString status() const { return m_status; }
    QUrl previewUrl() const { return m_previewUrl; }
    bool upscalerAvailable() const { return !upscalerPath().isEmpty(); }

    static QString upscalerPath();
    // Local AI (ONNX Runtime via system/ia-sms-ia.py, installed by
    // scripts/instalar-ia.sh): segmentation model and LaMa inpainting model.
    static QString aiPython();
    static QString aiScript();
    static QString aiModel(const QStringList &candidates);
    static QString segmentationModel();
    static QString inpaintModel();
    bool aiBackgroundAvailable() const { return !segmentationModel().isEmpty(); }
    bool aiFillAvailable() const { return !inpaintModel().isEmpty(); }

    Q_INVOKABLE bool previewCleanup(int index, const QString &maskPath, bool usePlate, int feather);
    Q_INVOKABLE bool previewChroma(int index, const QColor &key, double tolerance, double softness, bool spill,
                                   const QUrl &background);
    Q_INVOKABLE void clearPreview();

    Q_INVOKABLE bool applyCleanup(const QVariantList &indices, const QString &maskPath, bool usePlate, int feather);
    Q_INVOKABLE bool applyChroma(const QVariantList &indices, const QColor &key, double tolerance, double softness,
                                 bool spill, const QUrl &background);
    Q_INVOKABLE bool upscale(const QVariantList &indices, int factor);
    Q_INVOKABLE int restore(const QVariantList &indices);

    // AI background removal (no green screen needed); empty background keeps
    // transparency.
    Q_INVOKABLE bool previewAiBackground(int index, const QUrl &background);
    Q_INVOKABLE bool applyAiBackground(const QVariantList &indices, const QUrl &background);
    // AI fill (LaMa) of the painted mask.
    Q_INVOKABLE bool previewAiFill(int index, const QString &maskPath);
    Q_INVOKABLE bool applyAiFill(const QVariantList &indices, const QString &maskPath);

    // Digital mouth replacement: composites, on each frame, the character's
    // mouth for the lip-sync shape given in `shapes` (frame index → "A".."X").
    // The mouth is centred at (cx, cy) (normalised) with `width` as a
    // fraction of the frame width.
    Q_INVOKABLE bool applyMouths(const QVariantList &indices, const QVariantMap &shapes, const QString &characterDir,
                                 double cx, double cy, double width);

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
    using FrameOperation = std::function<QImage(const QImage &, int frameIndex)>;
    bool runBatch(const QVariantList &indices, const QString &label, const Operation &op);
    bool runBatch(const QVariantList &indices, const QString &label, const FrameOperation &op);
    bool runPreview(int index, const Operation &op);
    void setStatus(const QString &status);
    void setProgress(double progress);
    // Runs ia-sms-ia.py on frames; preview when `previewIndex` >= 0.
    bool runAi(const QStringList &commandArgs, const QVariantList &indices, int previewIndex, const QString &label);

    ProjectManager *m_project;
    QFutureWatcher<QString> m_watcher; // result: status message ("" = ok)
    QProcess m_ai;
    QList<QPair<QString, QString>> m_aiPairs; // produced file → frame file
    QList<int> m_aiIndices;
    bool m_aiPreview = false;
    QString m_aiLabel;
    QList<int> m_touched;
    QUrl m_previewUrl;
    int m_previewRev = 0;
    QString m_status;
    double m_progress = 0.0;
};
