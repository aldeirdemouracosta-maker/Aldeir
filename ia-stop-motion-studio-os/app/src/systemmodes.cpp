#include "systemmodes.h"

#include <QCoreApplication>
#include <QFileInfo>
#include <QStandardPaths>

#include <unistd.h>

namespace {
const QStringList kModes{QStringLiteral("captura"), QStringLiteral("edicao"), QStringLiteral("ia"),
                         QStringLiteral("render"), QStringLiteral("normal")};
}

SystemModes::SystemModes(QObject *parent)
    : QObject(parent)
{
    m_debounce.setSingleShot(true);
    m_debounce.setInterval(800);
    connect(&m_debounce, &QTimer::timeout, this, &SystemModes::apply);
    connect(&m_helper, &QProcess::finished, this, [this](int code, QProcess::ExitStatus st) {
        const bool ok = st == QProcess::NormalExit && code == 0;
        const QString out = QString::fromUtf8(m_helper.readAllStandardOutput() + m_helper.readAllStandardError()).trimmed();
        m_lastMessage = ok ? tr("Modo %1 aplicado").arg(label(m_mode)) : tr("Não foi possível aplicar o modo: %1").arg(out.right(200));
        emit lastMessageChanged();
        emit applied(m_mode, ok);
        if (!m_pending.isEmpty() && m_pending != m_mode)
            m_debounce.start();
    });
}

QString SystemModes::helperPath()
{
    const QString env = qEnvironmentVariable("IA_SMS_MODE_HELPER");
    if (!env.isEmpty())
        return QFileInfo(env).isExecutable() ? env : QString();
    const QString installed = QStringLiteral("/usr/local/lib/ia-stop-motion/ia-sms-modo");
    return QFileInfo(installed).isExecutable() ? installed : QString();
}

QString SystemModes::modeFor(const QString &page, bool rendering, bool aiWorking)
{
    if (rendering)
        return QStringLiteral("render");
    if (aiWorking || page == QLatin1String("ia"))
        return QStringLiteral("ia");
    if (page == QLatin1String("captura") || page == QLatin1String("player"))
        return QStringLiteral("captura");
    if (page == QLatin1String("timeline") || page == QLatin1String("editor") || page == QLatin1String("renderizacao"))
        return QStringLiteral("edicao");
    return QStringLiteral("normal");
}

QString SystemModes::label(const QString &mode)
{
    if (mode == QLatin1String("captura")) return tr("Captura");
    if (mode == QLatin1String("edicao")) return tr("Edição");
    if (mode == QLatin1String("ia")) return tr("IA");
    if (mode == QLatin1String("render")) return tr("Render");
    return tr("Normal");
}

void SystemModes::setAutomatic(bool on)
{
    if (on == m_automatic)
        return;
    m_automatic = on;
    emit automaticChanged();
}

void SystemModes::updateContext(const QString &page, bool rendering, bool aiWorking)
{
    if (m_automatic)
        setMode(modeFor(page, rendering, aiWorking));
}

void SystemModes::setMode(const QString &mode)
{
    if (!kModes.contains(mode))
        return;
    m_pending = mode;
    if (mode != m_mode || m_helper.state() != QProcess::NotRunning)
        m_debounce.start();
}

void SystemModes::apply()
{
    if (m_pending.isEmpty() || m_helper.state() != QProcess::NotRunning)
        return;
    const QString mode = m_pending;
    m_pending.clear();
    if (mode == m_mode && !m_lastMessage.isEmpty())
        return;
    m_mode = mode;
    emit modeChanged();

    const QString helper = helperPath();
    if (helper.isEmpty()) {
        m_lastMessage = tr("Modo %1 (ajustes do sistema não instalados: scripts/instalar-modos.sh)").arg(label(mode));
        emit lastMessageChanged();
        emit applied(mode, false);
        return;
    }
    const QStringList args{mode, QStringLiteral("--pid"), QString::number(QCoreApplication::applicationPid())};
    // Root (e.g. kiosk session) or a test helper run directly; otherwise pkexec.
    if (::geteuid() == 0 || !qEnvironmentVariableIsEmpty("IA_SMS_MODE_HELPER"))
        m_helper.start(helper, args);
    else
        m_helper.start(QStringLiteral("pkexec"), QStringList{helper} + args);
}
