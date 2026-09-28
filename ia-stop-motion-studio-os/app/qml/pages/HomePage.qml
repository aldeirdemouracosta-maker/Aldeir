import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import StopMotionStudio

Item {
    id: home
    signal navigate(string page)
    // Scales the hero (logo + title) down on narrower screens.
    readonly property real k: Math.max(0.7, Math.min(1, (width - 350) / 780))

    RowLayout {
        anchors.fill: parent
        spacing: 20

        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true

            ColumnLayout {
                x: 16; y: 16
                spacing: 18

                RowLayout {
                    spacing: 24
                    Clapperboard { Layout.preferredWidth: 200 * home.k; Layout.preferredHeight: 230 * home.k }
                    ColumnLayout {
                        spacing: -8
                        Text { text: "IA"; color: Theme.cream; font.pixelSize: 78 * home.k; font.weight: Font.Black; style: Text.Raised; styleColor: "#6B5A45" }
                        Text { text: "STOP-MOTION"; color: Theme.cream; font.pixelSize: 64 * home.k; font.weight: Font.Black; style: Text.Raised; styleColor: "#6B5A45" }
                        RowLayout {
                            spacing: 14
                            Text { text: "STUDIO"; color: Theme.felt; font.pixelSize: 64 * home.k; font.weight: Font.Black; style: Text.Raised; styleColor: "#123A70" }
                            Rectangle {
                                Layout.alignment: Qt.AlignVCenter
                                Layout.preferredWidth: 64 * home.k; Layout.preferredHeight: 44 * home.k; radius: 10; color: Theme.felt
                                border.color: "#123A70"; border.width: 2
                                Text { anchors.centerIn: parent; text: "OS"; color: "white"; font.pixelSize: 26 * home.k; font.weight: Font.Black }
                            }
                        }
                    }
                }
                Text {
                    text: "C A P T U R E   •   A N I M A T E   •   E D I T   •   R E N D E R"
                    color: Theme.text; font.pixelSize: 16 * home.k; font.weight: Font.DemiBold
                }
                Column {
                    spacing: 6
                    Text { text: "Sua criatividade quadro a quadro."; color: Theme.text; font.pixelSize: 30 * home.k; font.italic: true; font.family: "serif" }
                    Rectangle { width: 240; height: 3; radius: 2; color: Theme.accent }
                }

                RowLayout {
                    Layout.topMargin: 18
                    spacing: 0
                    Repeater {
                        model: [
                            { icon: "camera", text: "CAPTURA\nFRAME A FRAME", page: "captura" },
                            { icon: "chip", text: "IA LOCAL\nGRATUITA", page: "ia" },
                            { icon: "cube", text: "RIGGING E\nCENÁRIOS", page: "cenarios" },
                            { icon: "clapper", text: "DO ROTEIRO\nAO FILME", page: "renderizacao" }
                        ]
                        delegate: Rectangle {
                            width: 116; height: 104
                            color: area.containsMouse ? "#18FFFFFF" : "transparent"
                            radius: 10
                            Rectangle { visible: index > 0; width: 1; height: 70; color: "#33FFFFFF"; anchors.verticalCenter: parent.verticalCenter }
                            Column {
                                anchors.centerIn: parent
                                spacing: 10
                                Image { source: Theme.icon(modelData.icon); width: 40; height: 40; sourceSize: Qt.size(80, 80); anchors.horizontalCenter: parent.horizontalCenter }
                                Text { text: modelData.text; color: Theme.text; font.pixelSize: 12; horizontalAlignment: Text.AlignHCenter; anchors.horizontalCenter: parent.horizontalCenter }
                            }
                            MouseArea { id: area; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: home.navigate(modelData.page) }
                        }
                    }
                }

                RowLayout {
                    Layout.topMargin: 12
                    spacing: 12
                    IconButton {
                        iconName: "camera"; text: project.frameCount > 0 ? "Continuar captura" : "Começar captura"
                        highlighted: true
                        onClicked: home.navigate("captura")
                    }
                    IconButton {
                        iconName: "plus"; text: "Novo projeto"
                        onClicked: { project.newProject("Novo Projeto"); home.navigate("captura") }
                    }
                }
            }

            Text {
                anchors.right: parent.right; anchors.bottom: parent.bottom
                anchors.rightMargin: 12; anchors.bottomMargin: 4
                text: "“Grandes histórias\n também nascem\n  quadro a quadro.”"
                color: Theme.text; font.pixelSize: 22; font.italic: true; font.family: "serif"
                rotation: -4
            }
        }

        SystemPanel {
            Layout.preferredWidth: 330
            Layout.fillWidth: false
            Layout.alignment: Qt.AlignTop
            onOpenProject: (path) => { project.openProject(path); home.navigate("captura") }
        }
    }
}
