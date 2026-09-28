#pragma once

#include <QObject>
#include <QTimer>

// Lightweight system telemetry for the "Sistema" panel: CPU and RAM from
// /proc, GPU load/VRAM/temperature from the amdgpu sysfs interface.
class SystemMonitor : public QObject
{
    Q_OBJECT
    Q_PROPERTY(double cpu READ cpu NOTIFY updated)
    Q_PROPERTY(double ram READ ram NOTIFY updated)
    Q_PROPERTY(double gpu READ gpu NOTIFY updated)
    Q_PROPERTY(bool gpuAvailable READ gpuAvailable NOTIFY updated)
    Q_PROPERTY(double vramUsedMiB READ vramUsedMiB NOTIFY updated)
    Q_PROPERTY(double vramTotalMiB READ vramTotalMiB NOTIFY updated)
    Q_PROPERTY(double gpuTemp READ gpuTemp NOTIFY updated)
    Q_PROPERTY(double storageFreeGiB READ storageFreeGiB NOTIFY updated)
    Q_PROPERTY(double storageTotalGiB READ storageTotalGiB NOTIFY updated)

public:
    explicit SystemMonitor(const QString &storagePath, QObject *parent = nullptr);

    double cpu() const { return m_cpu; }
    double ram() const { return m_ram; }
    double gpu() const { return m_gpu; }
    bool gpuAvailable() const { return !m_gpuDevice.isEmpty(); }
    double vramUsedMiB() const { return m_vramUsed; }
    double vramTotalMiB() const { return m_vramTotal; }
    double gpuTemp() const { return m_gpuTemp; }
    double storageFreeGiB() const { return m_storageFree; }
    double storageTotalGiB() const { return m_storageTotal; }

signals:
    void updated();

private:
    void refresh();
    void readCpu();
    void readRam();
    void readGpu();
    void readStorage();

    QTimer m_timer;
    QString m_storagePath;
    QString m_gpuDevice; // e.g. /sys/class/drm/card0/device
    QString m_gpuTempFile;
    quint64 m_prevIdle = 0;
    quint64 m_prevTotal = 0;
    double m_cpu = 0, m_ram = 0, m_gpu = 0;
    double m_vramUsed = 0, m_vramTotal = 0, m_gpuTemp = 0;
    double m_storageFree = 0, m_storageTotal = 0;
};
