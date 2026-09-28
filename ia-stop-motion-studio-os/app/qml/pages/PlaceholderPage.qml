import QtQuick
import QtQuick.Layouts
import StopMotionStudio

// Screens from the mockup that are planned for later implementation steps.
Rectangle {
    id: page
    property string title
    property string iconName
    property int step
    property string description

    radius: Theme.radius
    color: Theme.panel
    border.color: "#1FFFFFFF"

    ColumnLayout {
        anchors.centerIn: parent
        width: Math.min(parent.width - 80, 640)
        spacing: 16
        Image { source: Theme.icon(page.iconName); Layout.preferredWidth: 72; Layout.preferredHeight: 72; sourceSize: Qt.size(144, 144); Layout.alignment: Qt.AlignHCenter }
        Text { text: page.title; color: Theme.text; font.pixelSize: 30; font.weight: Font.DemiBold; Layout.alignment: Qt.AlignHCenter }
        Text {
            text: page.description
            color: Theme.textDim; font.pixelSize: 16
            wrapMode: Text.WordWrap; horizontalAlignment: Text.AlignHCenter
            Layout.fillWidth: true
        }
        Rectangle {
            visible: page.step > 1
            Layout.alignment: Qt.AlignHCenter
            radius: 14; color: Theme.accentSoft; border.color: Theme.accent
            implicitWidth: badge.implicitWidth + 28; implicitHeight: 30
            Text { id: badge; anchors.centerIn: parent; text: "Planejado para a etapa " + page.step + " do roteiro"; color: Theme.text; font.pixelSize: 13 }
        }
    }
}
