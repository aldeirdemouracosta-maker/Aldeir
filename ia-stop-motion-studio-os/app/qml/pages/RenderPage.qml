import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import StopMotionStudio

Rectangle {
    id: page
    radius: Theme.radius
    color: Theme.panel
    border.color: "#1FFFFFFF"

    property string preset: "youtube"
    property bool useGpu: exporter.vaapiAvailable

    readonly property var presetInfo: [
        { id: "youtube", title: "YouTube", sub: "16:9 · 1920×1080", w: 16, h: 9 },
        { id: "vertical", title: "Reels / TikTok", sub: "9:16 · 1080×1920", w: 9, h: 16 },
        { id: "quadrado", title: "Quadrado", sub: "1:1 · 1080×1080", w: 1, h: 1 },
        { id: "4k", title: "4K", sub: "16:9 · 3840×2160 (lento)", w: 16, h: 9 }
    ]

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 28
        spacing: 18

        Text { text: "Renderização"; color: Theme.text; font.pixelSize: 28; font.weight: Font.DemiBold }
        Text {
            text: (project.projectName || "Sem projeto") + "  ·  " + project.frameCount + " fotos  ·  "
                  + project.totalFrames + " quadros  ·  " + project.fps + " fps  ·  " + project.durationText
                  + (project.audioName ? "  ·  ♪ " + project.audioName : "")
            color: Theme.textDim; font.pixelSize: 15
        }

        RowLayout {
            spacing: 14
            Repeater {
                model: page.presetInfo
                delegate: Rectangle {
                    width: 200; height: 170; radius: 12
                    color: page.preset === modelData.id ? Theme.accentSoft : "#14FFFFFF"
                    border.color: page.preset === modelData.id ? Theme.accent : "#22FFFFFF"
                    border.width: 2
                    Column {
                        anchors.centerIn: parent
                        spacing: 10
                        Rectangle {
                            anchors.horizontalCenter: parent.horizontalCenter
                            readonly property real s: 70 / Math.max(modelData.w, modelData.h)
                            width: modelData.w * s; height: modelData.h * s
                            radius: 4; color: "transparent"; border.color: Theme.text; border.width: 2
                        }
                        Text { text: modelData.title; color: Theme.text; font.pixelSize: 17; font.weight: Font.DemiBold; anchors.horizontalCenter: parent.horizontalCenter }
                        Text { text: modelData.sub; color: Theme.textDim; font.pixelSize: 12; anchors.horizontalCenter: parent.horizontalCenter }
                    }
                    MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: page.preset = modelData.id }
                }
            }
        }

        RowLayout {
            spacing: 10
            Switch {
                checked: project.deflicker
                onToggled: project.deflicker = checked
                focusPolicy: Qt.NoFocus
            }
            Text {
                text: "Remover flicker (iguala o brilho entre as fotos)"
                color: Theme.text; font.pixelSize: 14
            }
        }

        RowLayout {
            spacing: 10
            Switch {
                checked: page.useGpu
                enabled: exporter.vaapiAvailable
                onToggled: page.useGpu = checked
                focusPolicy: Qt.NoFocus
            }
            Text {
                text: exporter.vaapiAvailable ? "Usar o encoder da GPU (VAAPI)" : "Encoder da GPU indisponível — usando CPU (x264)"
                color: Theme.text; font.pixelSize: 14
            }
        }

        RowLayout {
            spacing: 12
            IconButton {
                iconName: "export"; text: exporter.busy ? "Exportando…" : "Exportar MP4"
                highlighted: true
                enabled: !exporter.busy && project.frameCount > 0
                onClicked: exporter.exportVideo(page.preset, page.useGpu)
            }
            IconButton { iconName: "stop"; text: "Cancelar"; visible: exporter.busy; onClicked: exporter.cancel() }
            IconButton {
                iconName: "folder"; text: "Abrir pasta"
                visible: exporter.lastOutput.length > 0
                onClicked: Qt.openUrlExternally("file://" + project.projectPath + "/export")
            }
        }

        ProgressBar {
            Layout.preferredWidth: 600
            value: exporter.progress
            visible: exporter.busy || exporter.progress > 0
        }
        Text { text: exporter.status; color: Theme.text; font.pixelSize: 14 }
        Item { Layout.fillHeight: true }
    }
}
