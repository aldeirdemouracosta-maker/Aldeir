#pragma once

#include <QObject>
#include <QProcess>
#include <QTimer>

// Performance modes of IA Stop-Motion Studio OS (Captura, Edição, IA,
// Render). In automatic mode the app picks the mode from what the user is
// doing; applying it runs the privileged helper `ia-sms-modo` through pkexec
// (allowed without a password by the installed polkit policy), which tunes
// the RX 580 power profile, the CPU governor, process priorities and — when
// available — the sched_ext CPU scheduler.
class SystemModes : public QObject
{
    Q_OBJECT
    Q_PROPERTY(QString mode READ mode NOTIFY modeChanged)
    Q_PROPERTY(QString modeLabel READ modeLabel NOTIFY modeChanged)
    Q_PROPERTY(bool automatic READ automatic WRITE setAutomatic NOTIFY automaticChanged)
    Q_PROPERTY(bool available READ available CONSTANT)
    Q_PROPERTY(QString lastMessage READ lastMessage NOTIFY lastMessageChanged)

public:
    explicit SystemModes(QObject *parent = nullptr);

    static QString helperPath();
    // Mode the app should be in, given the visible page and background work.
    static QString modeFor(const QString &page, bool rendering, bool aiWorking);
    static QString label(const QString &mode);

    QString mode() const { return m_mode; }
    QString modeLabel() const { return label(m_mode); }
    bool automatic() const { return m_automatic; }
    void setAutomatic(bool on);
    bool available() const { return !helperPath().isEmpty(); }
    QString lastMessage() const { return m_lastMessage; }

    // Called by the UI whenever the page or the busy state changes.
    Q_INVOKABLE void updateContext(const QString &page, bool rendering, bool aiWorking);
    Q_INVOKABLE void setMode(const QString &mode);

signals:
    void modeChanged();
    void automaticChanged();
    void lastMessageChanged();
    void applied(const QString &mode, bool ok);

private:
    void apply();

    QString m_mode = QStringLiteral("normal");
    QString m_pending;
    bool m_automatic = true;
    QString m_lastMessage;
    QTimer m_debounce; // avoid flapping while the user clicks around
    QProcess m_helper;
};
