#pragma once

#include <QImage>
#include <QMutex>
#include <QObject>
#include <QProcess>
#include <QQuickImageProvider>
#include <QVariantList>

// DSLR / mirrorless capture through the gphoto2 command-line tool
// (libgphoto2 supports 2,500+ cameras over USB):
//   - detection (gphoto2 --auto-detect)
//   - live view from the camera's movie stream (MJPEG over stdout)
//   - full-resolution capture, downloaded straight into the project
// Live view is paused while a photo is taken because the camera can only
// serve one gphoto2 session at a time.
class DslrCamera : public QObject
{
    Q_OBJECT
    Q_PROPERTY(bool available READ available CONSTANT)
    Q_PROPERTY(QVariantList cameras READ cameras NOTIFY camerasChanged)
    Q_PROPERTY(bool liveView READ liveView NOTIFY liveViewChanged)
    Q_PROPERTY(bool busy READ busy NOTIFY busyChanged)
    Q_PROPERTY(int frameCounter READ frameCounter NOTIFY liveFrame)
    Q_PROPERTY(QString status READ status NOTIFY statusChanged)

public:
    explicit DslrCamera(QObject *parent = nullptr);
    ~DslrCamera() override;

    static QString gphoto2Path();

    bool available() const { return !gphoto2Path().isEmpty(); }
    QVariantList cameras() const { return m_cameras; }
    bool liveView() const { return m_live.state() != QProcess::NotRunning; }
    bool busy() const { return m_capture.state() != QProcess::NotRunning || m_detect.state() != QProcess::NotRunning; }
    int frameCounter() const { return m_counter; }
    QString status() const { return m_status; }
    QImage latestFrame() const;

    Q_INVOKABLE void detect();
    Q_INVOKABLE void startLiveView(const QString &port);
    Q_INVOKABLE void stopLiveView();
    Q_INVOKABLE bool capture(const QString &port);

signals:
    void camerasChanged();
    void liveViewChanged();
    void busyChanged();
    void liveFrame();
    void statusChanged();
    void captured(const QImage &image);
    void captureFailed(const QString &message);

private:
    void setStatus(const QString &status);
    void parseStream();
    void startCapture();

    QProcess m_detect;
    QProcess m_live;
    QProcess m_capture;
    QVariantList m_cameras;
    QByteArray m_stream;
    mutable QMutex m_frameMutex;
    QImage m_frame;
    int m_counter = 0;
    QString m_status;
    QString m_livePort;
    QString m_capturePort;
    QString m_captureDir;
    bool m_resumeLive = false;
};

// Serves the live-view frame to QML as image://dslr/<counter>.
class DslrImageProvider : public QQuickImageProvider
{
public:
    explicit DslrImageProvider(DslrCamera *camera)
        : QQuickImageProvider(QQuickImageProvider::Image)
        , m_camera(camera)
    {
    }
    QImage requestImage(const QString &id, QSize *size, const QSize &requestedSize) override;

private:
    DslrCamera *m_camera;
};
