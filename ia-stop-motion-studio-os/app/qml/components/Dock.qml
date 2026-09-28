import QtQuick
import QtQuick.Layouts
import StopMotionStudio

// Bottom dock, as in the original mockup.
Rectangle {
    id: dock
    property string currentPage
    signal navigate(string page)

    implicitWidth: row.implicitWidth + 36
    implicitHeight: 104
    radius: 18
    color: "#D9121A2A"
    border.color: "#2EFFFFFF"

    readonly property var items: [
        { page: "projetos", label: "Arquivos", icon: "folder", color: "#3F8CFF" },
        { page: "captura", label: "Captura", icon: "camera", color: "#3A7BE0" },
        { page: "timeline", label: "Timeline", icon: "timeline", color: "#3D6FB8" },
        { page: "player", label: "Player", icon: "play", color: "#2A8CFF" },
        { page: "biblioteca", label: "Biblioteca", icon: "library", color: "#4D8FE8" },
        { page: "ia", label: "IA Local", icon: "network", color: "#3570C8" },
        { page: "personagens", label: "Personagens", icon: "user", color: "#3C86F0" },
        { page: "cenarios", label: "Cenários", icon: "image", color: "#4A7FE0" },
        { page: "configuracoes", label: "Configurações", icon: "settings", color: "#3A78D8" },
        { separator: true },
        { page: "terminal", label: "Terminal", icon: "terminal", color: "#1D2433" },
        { page: "lixeira", label: "Lixeira", icon: "trash", color: "#5B6F92" }
    ]

    RowLayout {
        id: row
        anchors.centerIn: parent
        spacing: 12
        Repeater {
            model: dock.items
            delegate: Loader {
                sourceComponent: modelData.separator ? sep : entry
                property var item: modelData
            }
        }
    }

    Component {
        id: sep
        Rectangle { width: 1; height: 64; color: "#33FFFFFF" }
    }
    Component {
        id: entry
        Item {
            width: 82; height: 88
            readonly property bool active: dock.currentPage === item.page
            Rectangle {
                id: tile
                width: 52; height: 52; radius: 12
                anchors.horizontalCenter: parent.horizontalCenter
                y: area.containsMouse ? 0 : 4
                Behavior on y { NumberAnimation { duration: 120 } }
                gradient: Gradient {
                    GradientStop { position: 0; color: Qt.lighter(item.color, 1.35) }
                    GradientStop { position: 1; color: item.color }
                }
                border.color: parent.active ? "white" : "#33FFFFFF"
                Image { anchors.centerIn: parent; source: Theme.icon(item.icon); width: 30; height: 30; sourceSize: Qt.size(60, 60) }
            }
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                y: 62
                text: item.label; color: Theme.text; font.pixelSize: 13
            }
            Rectangle {
                visible: parent.active
                width: 70; height: 3; radius: 2; color: Theme.accent
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.bottom: parent.bottom
            }
            MouseArea { id: area; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: dock.navigate(item.page) }
        }
    }
}
