import QtQuick
import StopMotionStudio

// Felt-style clapperboard logo drawn with plain shapes (scales to any size).
Item {
    id: root
    implicitWidth: 180
    implicitHeight: 160
    property bool showEyes: true

    // striped clapper arm
    Item {
        id: arm
        x: 0; y: 0
        width: root.width; height: root.height * 0.22
        rotation: -8
        transformOrigin: Item.BottomLeft
        clip: true
        Rectangle { anchors.fill: parent; radius: height * 0.15; color: "#F2EDE4" }
        Row {
            anchors.fill: parent
            Repeater {
                model: 6
                Rectangle {
                    width: arm.width / 6; height: arm.height
                    color: index % 2 ? "transparent" : "#1B1B1F"
                    antialiasing: true
                    transform: Matrix4x4 { matrix: Qt.matrix4x4(1, -0.6, 0, arm.height * 0.3, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1) }
                }
            }
        }
    }
    // body
    Rectangle {
        id: body
        y: root.height * 0.27
        width: root.width; height: root.height * 0.73
        radius: height * 0.12
        color: Theme.felt
        border.color: Qt.darker(Theme.felt, 1.4)
        border.width: Math.max(1, root.width * 0.02)

        // play triangle
        Canvas {
            id: tri
            width: body.width * 0.36; height: body.height * 0.55
            x: body.width * 0.14; anchors.verticalCenter: parent.verticalCenter
            onPaint: {
                const c = getContext("2d")
                c.reset()
                c.fillStyle = "#15171C"
                c.beginPath(); c.moveTo(0, 0); c.lineTo(width, height / 2); c.lineTo(0, height); c.closePath(); c.fill()
            }
        }
        Row {
            visible: root.showEyes
            spacing: body.width * 0.04
            x: body.width * 0.55; y: body.height * 0.22
            Repeater {
                model: 2
                Rectangle {
                    width: body.width * 0.15; height: width; radius: width / 2; color: "white"
                    Rectangle { width: parent.width * 0.55; height: width; radius: width / 2; color: "#111"; anchors.centerIn: parent; anchors.horizontalCenterOffset: parent.width * 0.1 }
                }
            }
        }
    }
}
