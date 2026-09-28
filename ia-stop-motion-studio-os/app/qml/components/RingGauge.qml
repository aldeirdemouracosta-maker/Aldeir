import QtQuick
import StopMotionStudio

Item {
    id: ring
    property real value: 0 // 0..100
    property color color: Theme.accent
    property string label
    property string valueText: Math.round(value) + "%"
    implicitWidth: 88; implicitHeight: 88

    onValueChanged: canvas.requestPaint()

    Canvas {
        id: canvas
        anchors.fill: parent
        onPaint: {
            const c = getContext("2d")
            const r = width / 2 - 5
            c.reset()
            c.lineWidth = 6
            c.lineCap = "round"
            c.strokeStyle = "#2AFFFFFF"
            c.beginPath(); c.arc(width / 2, height / 2, r, 0, 2 * Math.PI); c.stroke()
            c.strokeStyle = ring.color
            c.beginPath()
            c.arc(width / 2, height / 2, r, -Math.PI / 2, -Math.PI / 2 + 2 * Math.PI * Math.max(0.01, ring.value / 100))
            c.stroke()
        }
    }
    Column {
        anchors.centerIn: parent
        Text { text: ring.label; color: Theme.textDim; font.pixelSize: 13; anchors.horizontalCenter: parent.horizontalCenter }
        Text { text: ring.valueText; color: Theme.text; font.pixelSize: 19; font.weight: Font.DemiBold; anchors.horizontalCenter: parent.horizontalCenter }
    }
}
