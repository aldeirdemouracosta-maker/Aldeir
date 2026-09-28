cmake_minimum_required(VERSION 3.16)
project(ia-stop-motion-studio-os VERSION 0.9.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)

find_package(Qt6 6.4 REQUIRED COMPONENTS Core Gui Concurrent Quick Multimedia Test)

# Core logic (projects, export, telemetry) shared by the app and the tests.
add_library(studio_core STATIC
    src/projectmanager.h src/projectmanager.cpp
    src/exporter.h src/exporter.cpp
    src/systemmonitor.h src/systemmonitor.cpp
    src/cameracontrol.h src/cameracontrol.cpp
    src/formats.h
    src/audiotrack.h src/audiotrack.cpp
    src/imagetools.h src/imagetools.cpp
    src/frametools.h src/frametools.cpp
    src/dslrcamera.h src/dslrcamera.cpp
    src/systemmodes.h src/systemmodes.cpp
    src/characters.h src/characters.cpp
    src/speechtools.h src/speechtools.cpp
    src/scenery.h src/scenery.cpp
    src/scene.h src/scene.cpp
    src/timeline.h src/timeline.cpp
    src/timelinerenderer.h src/timelinerenderer.cpp
    src/titlerenderer.h src/titlerenderer.cpp
)
target_include_directories(studio_core PUBLIC src)
target_link_libraries(studio_core PUBLIC Qt6::Core Qt6::Gui Qt6::Concurrent Qt6::Quick Qt6::Multimedia)

qt_add_executable(ia-stop-motion-studio src/main.cpp)

set_source_files_properties(qml/Theme.qml PROPERTIES QT_QML_SINGLETON_TYPE TRUE)

file(GLOB ICON_FILES RELATIVE ${CMAKE_CURRENT_SOURCE_DIR} icons/*.svg)

qt_add_qml_module(ia-stop-motion-studio
    URI StopMotionStudio
    VERSION 1.0
    QML_FILES
        qml/Main.qml
        qml/Theme.qml
        qml/components/TopBar.qml
        qml/components/Sidebar.qml
        qml/components/Dock.qml
        qml/components/SystemPanel.qml
        qml/components/RingGauge.qml
        qml/components/Clapperboard.qml
        qml/components/IconButton.qml
        qml/components/FrameSpin.qml
        qml/components/DopeSheet.qml
        qml/pages/HomePage.qml
        qml/pages/CapturePage.qml
        qml/pages/RenderPage.qml
        qml/pages/TimelinePage.qml
        qml/pages/AiPage.qml
        qml/pages/CharactersPage.qml
        qml/pages/SceneryPage.qml
        qml/pages/PlaceholderPage.qml
    RESOURCES ${ICON_FILES}
)

target_compile_definitions(ia-stop-motion-studio PRIVATE APP_VERSION="${PROJECT_VERSION}")
target_link_libraries(ia-stop-motion-studio PRIVATE studio_core Qt6::Quick)

enable_testing()
qt_add_executable(tst_project tests/tst_project.cpp)
target_link_libraries(tst_project PRIVATE studio_core Qt6::Test)
add_test(NAME tst_project COMMAND tst_project)
qt_add_executable(tst_timeline tests/tst_timeline.cpp)
target_link_libraries(tst_timeline PRIVATE studio_core Qt6::Test)
add_test(NAME tst_timeline COMMAND tst_timeline)
qt_add_executable(tst_audio tests/tst_audio.cpp)
target_link_libraries(tst_audio PRIVATE studio_core Qt6::Test)
add_test(NAME tst_audio COMMAND tst_audio)
qt_add_executable(tst_imagetools tests/tst_imagetools.cpp)
target_link_libraries(tst_imagetools PRIVATE studio_core Qt6::Test)
add_test(NAME tst_imagetools COMMAND tst_imagetools)
qt_add_executable(tst_dslr tests/tst_dslr.cpp)
target_link_libraries(tst_dslr PRIVATE studio_core Qt6::Test)
target_compile_definitions(tst_dslr PRIVATE MOCK_GPHOTO2="${CMAKE_CURRENT_SOURCE_DIR}/tests/mock-gphoto2.sh")
add_test(NAME tst_dslr COMMAND tst_dslr)
qt_add_executable(tst_modes tests/tst_modes.cpp)
target_link_libraries(tst_modes PRIVATE studio_core Qt6::Test)
add_test(NAME tst_modes COMMAND tst_modes)
qt_add_executable(tst_characters tests/tst_characters.cpp)
target_link_libraries(tst_characters PRIVATE studio_core Qt6::Test)
add_test(NAME tst_characters COMMAND tst_characters)
qt_add_executable(tst_speech tests/tst_speech.cpp)
target_link_libraries(tst_speech PRIVATE studio_core Qt6::Test)
target_compile_definitions(tst_speech PRIVATE
    MOCK_WHISPER="${CMAKE_CURRENT_SOURCE_DIR}/tests/mock-whisper-cli.sh"
    MOCK_PIPER="${CMAKE_CURRENT_SOURCE_DIR}/tests/mock-piper.sh")
add_test(NAME tst_speech COMMAND tst_speech)
qt_add_executable(tst_scenery tests/tst_scenery.cpp)
target_link_libraries(tst_scenery PRIVATE studio_core Qt6::Test)
target_compile_definitions(tst_scenery PRIVATE MOCK_SD="${CMAKE_CURRENT_SOURCE_DIR}/tests/mock-sd-cli.sh")
add_test(NAME tst_scenery COMMAND tst_scenery)
add_test(NAME ia_sms_modo COMMAND ${CMAKE_CURRENT_SOURCE_DIR}/../system/test-ia-sms-modo.sh)
set_tests_properties(tst_project tst_timeline tst_audio tst_imagetools tst_dslr tst_modes tst_characters tst_speech tst_scenery PROPERTIES ENVIRONMENT "QT_QPA_PLATFORM=offscreen")

install(TARGETS ia-stop-motion-studio RUNTIME DESTINATION bin)
