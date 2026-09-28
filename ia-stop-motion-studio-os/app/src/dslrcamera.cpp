#include "dslrcamera.h"

#include <QDir>
#include <QFileInfo>
#include <QImageReader>
#include <QStandardPaths>
#include <QCoreApplication>
#include <QRegularExpression>

DslrCamera::DslrCamera(QObject *parent)
    : QObject(parent)
    , m_captureDir(QDir::tempPath() + QStringLiteral("/ia-sms-dslr-%1").arg(QCoreApplication::applicationPid()))
{
    QDir().mkpath(m_captureDir);

    connect(&m_detect, &QProcess::stateChanged, this, &DslrCamera::busyChanged);
    connect(&m_detect, &QProcess::finished, this, [this] {
        m_cameras.clear();
        // Output: header, a dashed line, then "<model>   <port>" rows.
        const QStringList lines = QString::fromUtf8(m_detect.readAllStandardOutput()).split(QLatin1Char('\n'));
        bool table = false;
        for (const QString &raw : lines) {
            const QString line = raw.trimmed();
            if (line.startsWith(QLatin1String("---"))) { table = true; continue; }
            if (!table || line.trimmed().isEmpty())
                continue;
            const int portAt = line.lastIndexOf(QRegularExpression(QStringLiteral("\\s{2,}")));
            if (portAt <= 0)
                continue;
            const QString model = line.left(portAt).trimmed();
            const QString port = line.mid(portAt).trimmed();
            m_cameras.append(QVariantMap{{QStringLiteral("model"), model}, {QStringLiteral("port"), port}});
        }
        setStatus(m_cameras.isEmpty() ? tr("Nenhuma câmera gPhoto2 encontrada.") : QString());
        emit camerasChanged();
    });

    connect(&m_live, &QProcess::stateChanged, this, &DslrCamera::liveViewChanged);
    connect(&m_live, &QProcess::readyReadStandardOutput, this, &DslrCamera::parseStream);
    connect(&m_live, &QProcess::finished, this, [this] {
        m_stream.clear();
        if (!m_capturePort.isEmpty())
            startCapture(); // live view was stopped to free the camera
    });

    connect(&m_capture, &QProcess::stateChanged, this, &DslrCamera::busyChanged);
    connect(&m_capture, &QProcess::finished, this, [this](int code, QProcess::ExitStatus st) {
        const QString port = m_capturePort;
        m_capturePort.clear();
        QImage image;
        if (st == QProcess::NormalExit && code == 0) {
            // Prefer the JPEG when the camera shoots RAW+JPEG.
            const QDir dir(m_captureDir);
            QStringList files = dir.entryList({QStringLiteral("captura.*")}, QDir::Files);
            std::sort(files.begin(), files.end(), [](const QString &a, const QString &b) {
                const bool ja = a.endsWith(QLatin1String(".jpg"), Qt::CaseInsensitive);
                const bool jb = b.endsWith(QLatin1String(".jpg"), Qt::CaseInsensitive);
                return ja && !jb;
            });
            for (const QString &f : files) {
                if (image.isNull()) {
                    QImageReader reader(dir.absoluteFilePath(f));
                    reader.setAutoTransform(true);
                    image = reader.read();
                }
                QFile::remove(dir.absoluteFilePath(f));
            }
        }
        if (image.isNull()) {
            const QString err = QString::fromUtf8(m_capture.readAllStandardError()).trimmed();
            setStatus(tr("Falha ao fotografar: %1").arg(err.isEmpty() ? tr("sem imagem") : err.right(160)));
            emit captureFailed(m_status);
        } else {
            setStatus(QString());
            emit captured(image);
        }
        if (m_resumeLive) {
            m_resumeLive = false;
            startLiveView(port);
        }
    });
}

DslrCamera::~DslrCamera()
{
    for (QProcess *p : {&m_live, &m_capture, &m_detect}) {
        if (p->state() != QProcess::NotRunning) {
            p->kill();
            p->waitForFinished(1000);
        }
    }
    QDir(m_captureDir).removeRecursively();
}

QString DslrCamera::gphoto2Path()
{
    const QString env = qEnvironmentVariable("IA_SMS_GPHOTO2");
    if (!env.isEmpty() && QFileInfo(env).isExecutable())
        return env;
    return QStandardPaths::findExecutable(QStringLiteral("gphoto2"));
}

void DslrCamera::setStatus(const QString &status)
{
    if (m_status == status)
        return;
    m_status = status;
    emit statusChanged();
}

QImage DslrCamera::latestFrame() const
{
    QMutexLocker lock(&m_frameMutex);
    return m_frame;
}

void DslrCamera::detect()
{
    if (!available() || m_detect.state() != QProcess::NotRunning || liveView() || m_capture.state() != QProcess::NotRunning)
        return;
    m_detect.start(gphoto2Path(), {QStringLiteral("--auto-detect")});
}

void DslrCamera::startLiveView(const QString &port)
{
    if (!available() || liveView() || m_capture.state() != QProcess::NotRunning)
        return;
    m_livePort = port;
    m_stream.clear();
    QStringList args;
    if (!port.isEmpty())
        args << QStringLiteral("--port") << port;
    args << QStringLiteral("--stdout") << QStringLiteral("--capture-movie");
    m_live.start(gphoto2Path(), args);
}

void DslrCamera::stopLiveView()
{
    if (!liveView())
        return;
    m_live.terminate();
    if (!m_live.waitForFinished(1500))
        m_live.kill();
}

void DslrCamera::parseStream()
{
    m_stream += m_live.readAllStandardOutput();
    // Keep only the newest complete JPEG (SOI FFD8 … EOI FFD9).
    int end = -1, start = -1;
    for (int from = m_stream.size();;) {
        end = m_stream.lastIndexOf("\xFF\xD9", from - 1);
        if (end < 0)
            break;
        start = m_stream.lastIndexOf("\xFF\xD8", end);
        if (start >= 0)
            break;
        from = end;
    }
    if (start < 0 || end < 0) {
        if (m_stream.size() > 32 * 1024 * 1024)
            m_stream.clear(); // garbage guard
        return;
    }
    const QImage img = QImage::fromData(m_stream.mid(start, end + 2 - start), "JPG");
    m_stream.remove(0, end + 2);
    if (img.isNull())
        return;
    {
        QMutexLocker lock(&m_frameMutex);
        m_frame = img;
    }
    ++m_counter;
    emit liveFrame();
}

bool DslrCamera::capture(const QString &port)
{
    if (!available() || m_capture.state() != QProcess::NotRunning || !m_capturePort.isEmpty())
        return false;
    m_capturePort = port.isEmpty() ? QStringLiteral(" ") : port;
    if (liveView()) {
        m_resumeLive = true;
        setStatus(tr("Pausando a visualização para fotografar…"));
        stopLiveView(); // capture starts when the live process exits
        return true;
    }
    startCapture();
    return true;
}

void DslrCamera::startCapture()
{
    const QString port = m_capturePort.trimmed();
    QStringList args;
    if (!port.isEmpty())
        args << QStringLiteral("--port") << port;
    args << QStringLiteral("--capture-image-and-download") << QStringLiteral("--force-overwrite")
         << QStringLiteral("--filename") << m_captureDir + QStringLiteral("/captura.%C");
    setStatus(tr("Fotografando…"));
    m_capture.start(gphoto2Path(), args);
}

QImage DslrImageProvider::requestImage(const QString &, QSize *size, const QSize &requestedSize)
{
    QImage img = m_camera->latestFrame();
    if (img.isNull()) {
        img = QImage(16, 9, QImage::Format_RGB32);
        img.fill(Qt::black);
    }
    if (requestedSize.isValid() && requestedSize.width() > 0 && requestedSize.width() < img.width())
        img = img.scaledToWidth(requestedSize.width(), Qt::SmoothTransformation);
    if (size)
        *size = img.size();
    return img;
}
