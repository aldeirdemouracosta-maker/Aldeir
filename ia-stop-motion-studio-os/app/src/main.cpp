#include <QGuiApplication>
#include <QLocale>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QQuickWindow>
#include <QTimer>

#include "audiotrack.h"
#include "cameracontrol.h"
#include "characters.h"
#include "dslrcamera.h"
#include "exporter.h"
#include "frametools.h"
#include "projectmanager.h"
#include "speechtools.h"
#include "systemmodes.h"
#include "systemmonitor.h"
#include "timeline.h"
#include "timelinerenderer.h"

int main(int argc, char *argv[])
{
    // The UI is styled by hand; the Basic style keeps controls customizable.
    if (qEnvironmentVariableIsEmpty("QT_QUICK_CONTROLS_STYLE"))
        qputenv("QT_QUICK_CONTROLS_STYLE", "Basic");

    QGuiApplication app(argc, argv);
    QGuiApplication::setApplicationName(QStringLiteral("IA Stop-Motion Studio OS"));
    QGuiApplication::setApplicationVersion(QStringLiteral(APP_VERSION));
    QGuiApplication::setOrganizationName(QStringLiteral("IA Stop-Motion Studio OS"));
    QLocale::setDefault(QLocale(QLocale::Portuguese, QLocale::Brazil));

    ProjectManager project;
    Exporter exporter(&project);
    SystemMonitor monitor(project.baseDir());
    CameraControl cameraControl;
    AudioTrack audioTrack(&project);
    FrameTools frameTools(&project);
    DslrCamera dslr;
    SystemModes systemModes;
    CharacterLibrary characters;
    SpeechTools speech;
    characters.ensureDefault();
    QObject::connect(&dslr, &DslrCamera::captured, &project, &ProjectManager::ingestCapture);
    Timeline timeline(&project);
    TimelineRenderer timelineRenderer(&timeline);

    // Reopen the most recent project so the studio resumes where it stopped.
    const QVariantList recent = project.recentProjects();
    if (!recent.isEmpty())
        project.openProject(recent.first().toMap().value(QStringLiteral("path")).toString());

    QQmlApplicationEngine engine;
    engine.rootContext()->setContextProperty(QStringLiteral("project"), &project);
    engine.rootContext()->setContextProperty(QStringLiteral("exporter"), &exporter);
    engine.rootContext()->setContextProperty(QStringLiteral("systemMonitor"), &monitor);
    engine.rootContext()->setContextProperty(QStringLiteral("cameraControl"), &cameraControl);
    engine.rootContext()->setContextProperty(QStringLiteral("timeline"), &timeline);
    engine.rootContext()->setContextProperty(QStringLiteral("audioTrack"), &audioTrack);
    engine.rootContext()->setContextProperty(QStringLiteral("frameTools"), &frameTools);
    engine.rootContext()->setContextProperty(QStringLiteral("dslr"), &dslr);
    engine.rootContext()->setContextProperty(QStringLiteral("systemModes"), &systemModes);
    engine.rootContext()->setContextProperty(QStringLiteral("characters"), &characters);
    engine.rootContext()->setContextProperty(QStringLiteral("speech"), &speech);
    engine.addImageProvider(QStringLiteral("dslr"), new DslrImageProvider(&dslr));
    engine.rootContext()->setContextProperty(QStringLiteral("timelineRenderer"), &timelineRenderer);
    engine.rootContext()->setContextProperty(QStringLiteral("appVersion"), QStringLiteral(APP_VERSION));

    QObject::connect(&engine, &QQmlApplicationEngine::objectCreationFailed, &app,
                     [] { QCoreApplication::exit(1); }, Qt::QueuedConnection);
    engine.load(QUrl(QStringLiteral("qrc:/StopMotionStudio/qml/Main.qml")));

    // --screenshot <file.png> [page]: render one page and exit (docs/CI).
    const QStringList args = app.arguments();
    const int shotIdx = args.indexOf(QStringLiteral("--screenshot"));
    if (shotIdx > 0 && shotIdx + 1 < args.size() && !engine.rootObjects().isEmpty()) {
        auto *window = qobject_cast<QQuickWindow *>(engine.rootObjects().first());
        const QString file = args.at(shotIdx + 1);
        if (shotIdx + 2 < args.size())
            window->setProperty("currentPage", args.at(shotIdx + 2));
        QTimer::singleShot(2500, window, [window, file] {
            window->grabWindow().save(file);
            QCoreApplication::quit();
        });
    }

    return app.exec();
}
