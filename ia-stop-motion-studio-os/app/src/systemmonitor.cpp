#include "systemmonitor.h"

#include <QDir>
#include <QFile>
#include <QStorageInfo>

namespace {

QByteArray readSysfs(const QString &path)
{
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly))
        return {};
    return file.readAll().trimmed();
}

} // namespace

SystemMonitor::SystemMonitor(const QString &storagePath, QObject *parent)
    : QObject(parent)
    , m_storagePath(storagePath)
{
    // Pick the first DRM card driven by amdgpu that reports GPU load.
    const QDir drm(QStringLiteral("/sys/class/drm"));
    for (const QString &card : drm.entryList({QStringLiteral("card?")}, QDir::Dirs | QDir::System)) {
        const QString dev = drm.absoluteFilePath(card) + QStringLiteral("/device");
        if (!QFile::exists(dev + QStringLiteral("/gpu_busy_percent")))
            continue;
        m_gpuDevice = dev;
        const QDir hwmon(dev + QStringLiteral("/hwmon"));
        const QStringList mons = hwmon.entryList(QDir::Dirs | QDir::NoDotAndDotDot);
        if (!mons.isEmpty())
            m_gpuTempFile = hwmon.absoluteFilePath(mons.first()) + QStringLiteral("/temp1_input");
        break;
    }

    connect(&m_timer, &QTimer::timeout, this, &SystemMonitor::refresh);
    m_timer.start(1500);
    refresh();
}

void SystemMonitor::refresh()
{
    readCpu();
    readRam();
    readGpu();
    readStorage();
    emit updated();
}

void SystemMonitor::readCpu()
{
    const QList<QByteArray> fields = readSysfs(QStringLiteral("/proc/stat")).split('\n').value(0).simplified().split(' ');
    if (fields.size() < 5)
        return;
    quint64 total = 0;
    for (int i = 1; i < fields.size(); ++i)
        total += fields.at(i).toULongLong();
    const quint64 idle = fields.at(4).toULongLong() + (fields.size() > 5 ? fields.at(5).toULongLong() : 0);
    if (m_prevTotal > 0 && total > m_prevTotal)
        m_cpu = 100.0 * (1.0 - double(idle - m_prevIdle) / double(total - m_prevTotal));
    m_prevIdle = idle;
    m_prevTotal = total;
}

void SystemMonitor::readRam()
{
    quint64 total = 0, available = 0;
    for (const QByteArray &line : readSysfs(QStringLiteral("/proc/meminfo")).split('\n')) {
        const QList<QByteArray> parts = line.simplified().split(' ');
        if (parts.size() < 2)
            continue;
        if (parts.first() == "MemTotal:")
            total = parts.at(1).toULongLong();
        else if (parts.first() == "MemAvailable:")
            available = parts.at(1).toULongLong();
    }
    if (total > 0)
        m_ram = 100.0 * double(total - available) / double(total);
}

void SystemMonitor::readGpu()
{
    if (m_gpuDevice.isEmpty())
        return;
    m_gpu = readSysfs(m_gpuDevice + QStringLiteral("/gpu_busy_percent")).toDouble();
    m_vramUsed = readSysfs(m_gpuDevice + QStringLiteral("/mem_info_vram_used")).toDouble() / (1024.0 * 1024.0);
    m_vramTotal = readSysfs(m_gpuDevice + QStringLiteral("/mem_info_vram_total")).toDouble() / (1024.0 * 1024.0);
    if (!m_gpuTempFile.isEmpty())
        m_gpuTemp = readSysfs(m_gpuTempFile).toDouble() / 1000.0;
}

void SystemMonitor::readStorage()
{
    const QStorageInfo info(m_storagePath);
    m_storageFree = double(info.bytesAvailable()) / (1024.0 * 1024.0 * 1024.0);
    m_storageTotal = double(info.bytesTotal()) / (1024.0 * 1024.0 * 1024.0);
}
