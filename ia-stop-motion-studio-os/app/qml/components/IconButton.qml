import QtQuick
import QtQuick.Controls
import StopMotionStudio

// Rounded button with an SVG icon and optional label, used in toolbars.
AbstractButton {
    id: control
    property string iconName
    property bool highlighted: false
    property color tint: highlighted ? Theme.accent : "#22FFFFFF"
    property string tip

    implicitHeight: 40
    implicitWidth: text.length > 0 ? row.implicitWidth + 24 : 40
    hoverEnabled: true
    focusPolicy: Qt.NoFocus

    ToolTip.visible: tip.length > 0 && hovered
    ToolTip.text: tip
    ToolTip.delay: 500

    background: Rectangle {
        radius: 10
        color: control.down ? Qt.darker(control.tint, 1.3)
             : control.hovered ? Qt.lighter(control.tint, 1.25) : control.tint
        border.color: control.highlighted ? Qt.lighter(Theme.accent, 1.3) : "transparent"
        opacity: control.enabled ? 1 : 0.4
    }

    contentItem: Item {
        Row {
            id: row
            anchors.centerIn: parent
            spacing: 8
            Image {
                source: control.iconName ? Theme.icon(control.iconName) : ""
                visible: control.iconName.length > 0
                width: 20; height: 20
                sourceSize: Qt.size(40, 40)
                anchors.verticalCenter: parent.verticalCenter
                opacity: control.enabled ? 1 : 0.5
            }
            Text {
                text: control.text
                visible: text.length > 0
                color: Theme.text
                font.pixelSize: 14
                anchors.verticalCenter: parent.verticalCenter
            }
        }
    }
}
