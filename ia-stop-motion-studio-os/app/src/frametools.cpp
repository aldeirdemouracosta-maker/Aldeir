#include "frametools.h"
#include "imagetools.h"
#include "projectmanager.h"

#include <QDir>
#include <QFileInfo>
#include <QImageReader>
#include <QProcess>
#include <QSaveFile>
#include <QStandardPaths>
#include <QtConcurrent>

namespace {

bool savePng(const QImage &image, const QString &path)
{
    QSaveFile file(path);
    if (!file.open(QIODevice::WriteOnly) || !image.save(&file, "PNG"))
        return false;
    return file.commit();
}

QImage readImage(const QString &path)
{
    QImageReader reader(path);
    reader.setAutoTransform(true);
    return reader.read();
}

} // namespace

FrameTools::FrameTools(ProjectManager *project, QObject *parent)
    : QObject(parent)
    , m_project(project)
{
    connect(&m_watcher, &QFutureWatcher<QString>::started, this, &FrameTools::busyChanged);
    connect(&m_watcher, &QFutureWatcher<QString>::finished, this, [this] {
        const QString error = m_watcher.result();
        if (!m_touched.isEmpty())
            m_project->framesModified(m_touched);
        m_touched.clear();
        setProgress(error.isEmpty() ? 1.0 : m_progress);
        if (!error.isEmpty())
            setStatus(error);
        emit busyChanged();
        emit finished(error.isEmpty(), m_status);
    });
    connect(project, &ProjectManager::projectChanged, this, &FrameTools::clearPreview);
}

FrameTools::~FrameTools()
{
    m_watcher.waitForFinished();
}

QString FrameTools::upscalerPath()
{
    const QString env = qEnvironmentVariable("IA_SMS_REALESRGAN");
    if (!env.isEmpty() && QFileInfo(env).isExecutable())
        return env;
    const QString found = QStandardPaths::findExecutable(QStringLiteral("realesrgan-ncnn-vulkan"));
    if (!found.isEmpty())
        return found;
    const QString home = qEnvironmentVariable("IA_SMS_HOME", QDir::homePath() + QStringLiteral("/IA-StopMotion"));
    const QString bundled = home + QStringLiteral("/ferramentas/realesrgan/realesrgan-ncnn-vulkan");
    return QFileInfo(bundled).isExecutable() ? bundled : QString();
}

void FrameTools::setStatus(const QString &status)
{
    if (m_status == status)
        return;
    m_status = status;
    emit statusChanged();
}

void FrameTools::setProgress(double progress)
{
    m_progress = progress;
    emit progressChanged();
}

void FrameTools::clearPreview()
{
    if (m_previewUrl.isEmpty())
        return;
    m_previewUrl = QUrl();
    emit previewChanged();
}

bool FrameTools::runPreview(int index, const Operation &op)
{
    if (busy() || index < 0 || index >= m_project->frameCount())
        return false;
    const QString src = m_project->frameFile(index);
    const QString out = m_project->projectPath() + QStringLiteral("/export/.previa.png");
    QDir().mkpath(QFileInfo(out).absolutePath());
    setStatus(tr("Gerando prévia…"));
    m_touched.clear();
    m_watcher.setFuture(QtConcurrent::run([=]() -> QString {
        const QImage result = op(readImage(src));
        if (result.isNull() || !savePng(result, out))
            return tr("Falha ao gerar a prévia.");
        QMetaObject::invokeMethod(this, [this, out] {
            m_previewUrl = QUrl::fromLocalFile(out);
            m_previewUrl.setQuery(QStringLiteral("v=%1").arg(++m_previewRev));
            emit previewChanged();
            setStatus(tr("Prévia pronta — compare antes/depois e aplique."));
        }, Qt::QueuedConnection);
        return {};
    }));
    return true;
}

bool FrameTools::runBatch(const QVariantList &indices, const QString &label, const Operation &op)
{
    if (busy() || indices.isEmpty())
        return false;
    QList<int> list;
    QStringList files;
    for (const QVariant &v : indices) {
        const int i = v.toInt();
        if (i < 0 || i >= m_project->frameCount())
            continue;
        if (!m_project->backupOriginal(i)) {
            setStatus(tr("Não foi possível guardar o original do quadro %1.").arg(i + 1));
            return false;
        }
        list << i;
        files << m_project->frameFile(i);
    }
    if (list.isEmpty())
        return false;
    clearPreview();
    m_touched = list;
    setProgress(0.0);
    setStatus(tr("%1: 0 de %2…").arg(label).arg(list.size()));
    m_watcher.setFuture(QtConcurrent::run([=]() -> QString {
        for (int k = 0; k < files.size(); ++k) {
            const QImage result = op(readImage(files.at(k)));
            if (result.isNull() || !savePng(result, files.at(k)))
                return tr("%1 falhou no quadro %2.").arg(label).arg(list.at(k) + 1);
            QMetaObject::invokeMethod(this, [this, k, n = files.size(), label] {
                setProgress(double(k + 1) / n);
                setStatus(tr("%1: %2 de %3…").arg(label).arg(k + 1).arg(n));
            }, Qt::QueuedConnection);
        }
        QMetaObject::invokeMethod(this, [this, label, n = files.size()] {
            setStatus(tr("%1 concluído em %2 quadro(s). Os originais ficam em originais/.").arg(label).arg(n));
        }, Qt::QueuedConnection);
        return {};
    }));
    return true;
}

// ── operations ───────────────────────────────────────────────────────────

bool FrameTools::previewCleanup(int index, const QString &maskPath, bool usePlate, int feather)
{
    const QImage mask(maskPath);
    const QImage plate = usePlate ? readImage(m_project->cleanPlateFile()) : QImage();
    if (mask.isNull() || (usePlate && plate.isNull())) {
        setStatus(usePlate && plate.isNull() ? tr("Defina uma placa limpa primeiro.") : tr("Pinte a área a limpar."));
        return false;
    }
    return runPreview(index, [=](const QImage &img) {
        return usePlate ? ImageTools::cleanWithPlate(img, plate, mask, feather) : ImageTools::fillMasked(img, mask);
    });
}

bool FrameTools::applyCleanup(const QVariantList &indices, const QString &maskPath, bool usePlate, int feather)
{
    const QImage mask(maskPath);
    const QImage plate = usePlate ? readImage(m_project->cleanPlateFile()) : QImage();
    if (mask.isNull() || (usePlate && plate.isNull())) {
        setStatus(usePlate && plate.isNull() ? tr("Defina uma placa limpa primeiro.") : tr("Pinte a área a limpar."));
        return false;
    }
    return runBatch(indices, tr("Limpeza"), [=](const QImage &img) {
        return usePlate ? ImageTools::cleanWithPlate(img, plate, mask, feather) : ImageTools::fillMasked(img, mask);
    });
}

bool FrameTools::previewChroma(int index, const QColor &key, double tolerance, double softness, bool spill,
                               const QUrl &background)
{
    const ImageTools::ChromaOptions o{key, tolerance, softness, spill};
    const QImage bg = background.isEmpty() ? QImage() : readImage(background.toLocalFile());
    return runPreview(index, [=](const QImage &img) { return ImageTools::chromaKey(img, o, bg); });
}

bool FrameTools::applyChroma(const QVariantList &indices, const QColor &key, double tolerance, double softness,
                             bool spill, const QUrl &background)
{
    const ImageTools::ChromaOptions o{key, tolerance, softness, spill};
    const QImage bg = background.isEmpty() ? QImage() : readImage(background.toLocalFile());
    return runBatch(indices, tr("Troca de fundo"), [=](const QImage &img) { return ImageTools::chromaKey(img, o, bg); });
}

bool FrameTools::upscale(const QVariantList &indices, int factor)
{
    const QString tool = upscalerPath();
    if (tool.isEmpty()) {
        setStatus(tr("Real-ESRGAN não instalado: rode scripts/instalar-realesrgan.sh"));
        return false;
    }
    // Photo model for 4×; the lighter animation model for 2×.
    const QString model = factor >= 4 ? QStringLiteral("realesrgan-x4plus") : QStringLiteral("realesr-animevideov3-x2");
    const QString scale = factor >= 4 ? QStringLiteral("4") : QStringLiteral("2");
    const QString models = QFileInfo(tool).absolutePath() + QStringLiteral("/models");
    const QString tmpDir = m_project->projectPath() + QStringLiteral("/export");
    QDir().mkpath(tmpDir);
    return runBatch(indices, tr("Upscale %1×").arg(scale), [=](const QImage &img) -> QImage {
        const QString in = tmpDir + QStringLiteral("/.upscale_in_%1.png").arg(quintptr(QThread::currentThreadId()));
        const QString out = tmpDir + QStringLiteral("/.upscale_out_%1.png").arg(quintptr(QThread::currentThreadId()));
        if (!img.save(in, "PNG"))
            return {};
        QProcess p;
        p.start(tool, {QStringLiteral("-i"), in, QStringLiteral("-o"), out, QStringLiteral("-n"), model,
                       QStringLiteral("-s"), scale, QStringLiteral("-m"), models});
        const bool ok = p.waitForFinished(-1) && p.exitStatus() == QProcess::NormalExit && p.exitCode() == 0;
        const QImage result = ok ? QImage(out) : QImage();
        QFile::remove(in);
        QFile::remove(out);
        return result;
    });
}

int FrameTools::restore(const QVariantList &indices)
{
    if (busy())
        return 0;
    int restored = 0;
    for (const QVariant &v : indices) {
        if (m_project->restoreOriginal(v.toInt()))
            ++restored;
    }
    clearPreview();
    setStatus(tr("%1 quadro(s) restaurado(s).").arg(restored));
    return restored;
}

QColor FrameTools::colorAt(int index, double nx, double ny) const
{
    const QImage img = readImage(m_project->frameFile(index));
    if (img.isNull())
        return {};
    const int x = qBound(0, int(nx * img.width()), img.width() - 1);
    const int y = qBound(0, int(ny * img.height()), img.height() - 1);
    // Average a small neighbourhood so noise does not skew the key colour.
    int r = 0, g = 0, b = 0, n = 0;
    for (int dy = -2; dy <= 2; ++dy) {
        for (int dx = -2; dx <= 2; ++dx) {
            const int xx = qBound(0, x + dx, img.width() - 1), yy = qBound(0, y + dy, img.height() - 1);
            const QRgb c = img.pixel(xx, yy);
            r += qRed(c); g += qGreen(c); b += qBlue(c); ++n;
        }
    }
    return QColor(r / n, g / n, b / n);
}
