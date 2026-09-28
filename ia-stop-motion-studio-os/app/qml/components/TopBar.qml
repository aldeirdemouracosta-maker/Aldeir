import QtQuick
import QtQuick.Layouts
import StopMotionStudio

Rectangle {
    id: bar
    height: Theme.topBarHeight
    color: "#E60A1120"

    property var now: new Date()
    Timer { interval: 1000; running: true; repeat: true; onTriggered: bar.now = new Date() }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 20
        anchors.rightMargin: 20
        spacing: 22

        Clapperboard { Layout.preferredWidth: 30; Layout.preferredHeight: 26 }
        Text {
            text: "IA Stop-Motion Studio OS"
            color: Theme.text
            font.pixelSize: 17
            font.weight: Font.DemiBold
        }
        Repeater {
            model: ["Arquivos", "Editar", "Visualizar", "Ferramentas", "Sistema", "Ajuda"]
            Text { text: modelData; color: Theme.text; font.pixelSize: 14; opacity: 0.9 }
        }
        Item { Layout.fillWidth: true }
        Repeater {
            model: ["search", "monitor"]
            Image { source: Theme.icon(modelData); sourceSize: Qt.size(36, 36); Layout.preferredWidth: 18; Layout.preferredHeight: 18 }
        }
        Text {
            // e.g. "Qui, 20 de Mar  13:33"
            text: {
                const d = bar.now.toLocaleDateString(Qt.locale("pt_BR"), "ddd, d 'de' MMM")
                return d.charAt(0).toUpperCase() + d.slice(1).replace(".", "") + "   " + Qt.formatTime(bar.now, "hh:mm")
            }
            color: Theme.text
            font.pixelSize: 14
        }
        Rectangle { width: 1; height: 22; color: Theme.panelBorder }
        Image { source: Theme.icon("user"); sourceSize: Qt.size(36, 36); Layout.preferredWidth: 18; Layout.preferredHeight: 18 }
        Text { text: "IA Stop-Motion Studio OS"; color: Theme.text; font.pixelSize: 14 }
    }

    Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: "#22FFFFFF" }
}
