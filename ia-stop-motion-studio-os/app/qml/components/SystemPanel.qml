import QtQuick
import QtQuick.Layouts
import StopMotionStudio

// Right-hand column of the home screen: "Sistema" and "Projeto Recente".
ColumnLayout {
    id: panel
    spacing: 14
    signal openProject(string path)

    readonly property var recent: project.recentProjects.length > 0 ? project.recentProjects[0] : null

    Rectangle {
        Layout.fillWidth: true
        Layout.preferredHeight: 290
        radius: Theme.radius
        color: Theme.panel
        border.color: "#1FFFFFFF"

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 18
            spacing: 10
            RowLayout {
                Text { text: "Sistema"; color: Theme.text; font.pixelSize: 17; font.weight: Font.DemiBold }
                Item { Layout.fillWidth: true }
                Text { text: "Ver detalhes  →"; color: Theme.accent; font.pixelSize: 14 }
            }
            RowLayout {
                Layout.fillWidth: true
                RingGauge { label: "CPU"; value: systemMonitor.cpu; color: Theme.cpu }
                Item { Layout.fillWidth: true }
                RingGauge { label: "RAM"; value: systemMonitor.ram; color: Theme.ram }
                Item { Layout.fillWidth: true }
                RingGauge {
                    label: "GPU"; value: systemMonitor.gpu; color: Theme.gpu
                    valueText: systemMonitor.gpuAvailable ? Math.round(value) + "%" : "—"
                }
            }
            Text {
                // VRAM and temperature are what limit an 8 GB RX 580.
                text: systemMonitor.gpuAvailable
                      ? "VRAM " + (systemMonitor.vramUsedMiB / 1024).toFixed(1) + " / " + (systemMonitor.vramTotalMiB / 1024).toFixed(1)
                        + " GB   ·   " + Math.round(systemMonitor.gpuTemp) + " °C"
                      : "GPU AMD não detectada"
                color: Theme.textDim; font.pixelSize: 13
            }
            Text {
                Layout.fillWidth: true
                elide: Text.ElideRight
                text: "Modo " + systemModes.modeLabel + (systemModes.automatic ? " (automático)" : "")
                      + (systemModes.available ? "" : " · ajustes do kernel não instalados")
                color: Theme.textDim; font.pixelSize: 13
            }
            Rectangle { Layout.fillWidth: true; height: 1; color: "#1FFFFFFF" }
            Text { text: "Armazenamento"; color: Theme.text; font.pixelSize: 15 }
            RowLayout {
                spacing: 12
                Image { source: Theme.icon("folder"); sourceSize: Qt.size(48, 48); Layout.preferredWidth: 26; Layout.preferredHeight: 26 }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 6
                    Text {
                        text: Math.round(systemMonitor.storageFreeGiB) + " GB livre de " + formatSize(systemMonitor.storageTotalGiB)
                        color: Theme.text; font.pixelSize: 14
                        function formatSize(g) { return g >= 1000 ? (g / 1024).toFixed(1) + " TB" : Math.round(g) + " GB" }
                    }
                    Rectangle {
                        Layout.fillWidth: true; height: 5; radius: 3; color: "#2AFFFFFF"
                        Rectangle {
                            height: parent.height; radius: 3; color: Theme.cpu
                            width: systemMonitor.storageTotalGiB > 0
                                   ? parent.width * (1 - systemMonitor.storageFreeGiB / systemMonitor.storageTotalGiB) : 0
                        }
                    }
                }
            }
        }
    }

    Rectangle {
        Layout.fillWidth: true
        Layout.preferredHeight: 262
        radius: Theme.radius
        color: Theme.panel
        border.color: "#1FFFFFFF"

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 18
            spacing: 10
            Text { text: "Projeto Recente"; color: Theme.text; font.pixelSize: 17; font.weight: Font.DemiBold }
            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                radius: 8
                color: "#1A2438"
                clip: true
                Image {
                    anchors.fill: parent
                    source: panel.recent ? panel.recent.thumbnail : ""
                    fillMode: Image.PreserveAspectCrop
                    asynchronous: true
                    sourceSize.width: 600
                }
                Text {
                    visible: !panel.recent || panel.recent.frames === 0
                    anchors.centerIn: parent
                    text: "Nenhum quadro ainda"
                    color: Theme.textDim
                }
                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    enabled: panel.recent !== null
                    onClicked: panel.openProject(panel.recent.path)
                }
            }
            RowLayout {
                Text {
                    text: panel.recent ? panel.recent.name : "Crie seu primeiro projeto"
                    color: Theme.text; font.pixelSize: 15; elide: Text.ElideRight
                    Layout.fillWidth: true
                }
                Text { text: "···"; color: Theme.text; font.pixelSize: 18 }
            }
            Text {
                text: panel.recent
                      ? (panel.recent.path === project.projectPath
                         ? project.durationText + "  ·  " + project.resolutionText + "  ·  " + project.fps + " fps"
                         : panel.recent.frames + " quadros  ·  " + panel.recent.fps + " fps")
                      : "Abra a Captura para começar"
                color: Theme.textDim; font.pixelSize: 13
            }
        }
    }
}
