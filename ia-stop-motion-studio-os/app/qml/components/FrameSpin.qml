import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import StopMotionStudio

// Labelled frame-count editor that displays seconds (e.g. "2,50 s").
ColumnLayout {
    id: root
    property string label
    property int value
    property int from: 0
    property int to: 100000
    property int fps: 24
    property int step: Math.max(1, Math.round(fps / 4))
    signal edited(int value)
    spacing: 2

    Text { text: root.label; color: Theme.textDim; font.pixelSize: 12 }
    SpinBox {
        id: spin
        Layout.fillWidth: true
        from: root.from
        to: root.to
        value: root.value
        stepSize: root.step
        editable: true
        focusPolicy: Qt.ClickFocus
        textFromValue: (v, locale) => Number(v / root.fps).toLocaleString(Qt.locale("pt_BR"), "f", 2) + " s"
        valueFromText: (text, locale) => Math.round(Number.fromLocaleString(Qt.locale("pt_BR"), text.replace(" s", "").trim()) * root.fps)
        validator: RegularExpressionValidator { regularExpression: /[0-9]+([,.][0-9]*)?( s)?/ }
        onValueModified: root.edited(value)
    }
}
