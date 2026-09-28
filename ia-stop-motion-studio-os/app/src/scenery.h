#pragma once

#include <QObject>
#include <QProcess>
#include <QUrl>
#include <QVariantList>

// Scenery library (<base>/Cenarios) shared by all projects: imported photos
// and backgrounds generated locally with stable-diffusion.cpp (sd-cli, Vulkan
// on the RX 580) using stop-motion style presets. Generated images keep a
// sidecar .json with the prompt and seed so they can be reproduced.
class SceneryStudio : public QObject
{
    Q_OBJECT
    Q_PROPERTY(QVariantList items READ items NOTIFY itemsChanged)
    Q_PROPERTY(QVariantList styles READ styles CONSTANT)
    Q_PROPERTY(bool generatorAvailable READ generatorAvailable CONSTANT)
    Q_PROPERTY(bool busy READ busy NOTIFY busyChanged)
    Q_PROPERTY(double progress READ progress NOTIFY progressChanged)
    Q_PROPERTY(QString status READ status NOTIFY statusChanged)
    Q_PROPERTY(QString baseDir READ baseDir CONSTANT)

public:
    explicit SceneryStudio(QObject *parent = nullptr);
    ~SceneryStudio() override;

    static QString sdPath();
    static QString sdModel();
    // Pixel size for a format id ("16:9", "9:16", "1:1") at SD 1.5 scale.
    static QSize sizeFor(const QString &format);
    // Full prompt for a style preset id.
    static QString stylePrompt(const QString &style, const QString &prompt);

    QVariantList items() const;
    QVariantList styles() const;
    bool generatorAvailable() const { return !sdPath().isEmpty() && !sdModel().isEmpty(); }
    bool busy() const { return m_proc.state() != QProcess::NotRunning; }
    double progress() const { return m_progress; }
    QString status() const { return m_status; }
    QString baseDir() const;

    Q_INVOKABLE bool generate(const QString &prompt, const QString &style, const QString &format, int steps, int seed);
    Q_INVOKABLE void cancel();
    Q_INVOKABLE int importImages(const QList<QUrl> &urls);
    Q_INVOKABLE bool remove(const QUrl &image);

signals:
    void itemsChanged();
    void busyChanged();
    void progressChanged();
    void statusChanged();
    void generated(const QUrl &image);
    void failed(const QString &message);

private:
    void setStatus(const QString &s);

    QProcess m_proc;
    QString m_output;
    QByteArray m_meta;
    double m_progress = 0;
    QString m_status;
    bool m_cancelled = false;
};
