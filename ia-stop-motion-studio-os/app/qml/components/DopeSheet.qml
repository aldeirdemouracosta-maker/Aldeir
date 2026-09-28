import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import StopMotionStudio

// Capture dope sheet: one column per video frame with the soundtrack's
// loudness, the lip-sync mouth shape and the photos (with their holds), plus
// the slot where the next photo will land.
Rectangle {
    id: sheet
    property int selected: -1
    property int cursorFrame: 0          // frame highlighted (next capture / playback)
    property bool playing: false
    signal selectPhoto(int index)
    signal importAudio()
    signal listen()

    readonly property real unit: 16      // pixels per video frame
    readonly property var starts: {
        let acc = 0, list = []
        for (const f of project.frames) { list.push(acc); acc += f.hold }
        return list
    }
    readonly property int columns: Math.max(project.totalFrames + 1, audioTrack.lengthFrames) + 12

    radius: 10
    color: Theme.panel
    border.color: "#1FFFFFFF"

    function shapeColor(s) {
        return ({ A: "#E57373", B: "#FFB74D", C: "#FFF176", D: "#81C784", E: "#4FC3F7",
                  F: "#9575CD", G: "#F06292", H: "#4DB6AC", X: "#90A4AE" })[s] || "#90A4AE"
    }

    onCursorFrameChanged: {
        // keep the cursor in view
        const x = cursorFrame * unit
        if (x < flick.contentX + 40) flick.contentX = Math.max(0, x - 40)
        else if (x > flick.contentX + flick.width - 80) flick.contentX = Math.min(flick.contentWidth - flick.width, x - flick.width + 80)
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 8
        spacing: 6

        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            Text { text: "Dope sheet"; color: Theme.text; font.pixelSize: 14; font.weight: Font.DemiBold }
            Text {
                text: project.audioName ? "♪ " + project.audioName : "Sem trilha de áudio"
                color: project.audioName ? Theme.text : Theme.textDim; font.pixelSize: 13
                elide: Text.ElideMiddle; Layout.maximumWidth: 220
            }
            IconButton { iconName: "import"; text: project.audioName ? "Trocar" : "Importar áudio"; implicitHeight: 30; onClicked: sheet.importAudio() }
            IconButton { iconName: "trash"; tip: "Remover a trilha"; implicitHeight: 30; implicitWidth: 30; visible: project.audioName.length > 0; onClicked: project.removeAudio() }
            IconButton {
                iconName: "play"; text: "Ouvir (A)"; implicitHeight: 30
                visible: project.audioName.length > 0
                tip: "Toca o áudio até o próximo quadro"
                onClicked: sheet.listen()
            }
            Text { visible: project.audioName.length > 0; text: "começa no quadro"; color: Theme.textDim; font.pixelSize: 12 }
            SpinBox {
                visible: project.audioName.length > 0
                implicitHeight: 30; implicitWidth: 110
                from: 0; to: 10000
                value: project.audioOffset
                editable: true
                focusPolicy: Qt.ClickFocus
                onValueModified: project.audioOffset = value
            }
            IconButton {
                iconName: "user"; text: audioTrack.busy ? "Analisando…" : "Sincronia labial"
                implicitHeight: 30
                visible: project.audioName.length > 0
                enabled: audioTrack.lipSyncAvailable && !audioTrack.busy
                tip: audioTrack.lipSyncAvailable ? "Calcula a boca de cada quadro com o Rhubarb Lip Sync"
                                                 : "Instale o Rhubarb: scripts/instalar-rhubarb.sh"
                onClicked: audioTrack.runLipSync()
            }
            Text { text: audioTrack.status; color: Theme.textDim; font.pixelSize: 12; elide: Text.ElideRight; Layout.fillWidth: true }
        }

        Flickable {
            id: flick
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            contentWidth: sheet.columns * sheet.unit
            contentHeight: height
            boundsBehavior: Flickable.StopAtBounds
            flickableDirection: Flickable.HorizontalFlick
            ScrollBar.horizontal: ScrollBar { policy: ScrollBar.AsNeeded }

            Item {
                width: flick.contentWidth
                height: flick.height

                // frame numbers
                Repeater {
                    model: Math.ceil(sheet.columns / 6)
                    Text {
                        x: index * 6 * sheet.unit + 2; y: 0
                        text: index * 6 + 1
                        color: index * 6 % project.fps === 0 ? Theme.text : Theme.textDim
                        font.pixelSize: 10
                    }
                }
                Repeater {
                    model: Math.ceil(sheet.columns / project.fps)
                    Rectangle { x: index * project.fps * sheet.unit; y: 12; width: 1; height: parent.height - 12; color: "#33FFFFFF" }
                }

                // waveform
                Repeater {
                    model: audioTrack.waveform
                    Rectangle {
                        x: index * sheet.unit + 1
                        width: sheet.unit - 2
                        height: Math.max(2, modelData * 30)
                        y: 14 + (32 - height) / 2
                        radius: 2
                        color: index === sheet.cursorFrame ? "#FFFFFF" : "#6FB3FF"
                        opacity: 0.85
                    }
                }

                // mouth shapes (label where the shape changes)
                Repeater {
                    model: audioTrack.mouths
                    Rectangle {
                        readonly property bool change: index === 0 || audioTrack.mouths[index - 1] !== modelData
                        visible: modelData !== ""
                        x: index * sheet.unit; y: 48
                        width: sheet.unit; height: 20
                        color: Qt.rgba(0, 0, 0, 0)
                        Rectangle { anchors.fill: parent; anchors.margins: 1; radius: 3; color: sheet.shapeColor(modelData); opacity: parent.change ? 0.95 : 0.35 }
                        Text { anchors.centerIn: parent; visible: parent.change; text: modelData; color: "#111"; font.pixelSize: 12; font.weight: Font.Bold }
                    }
                }

                // photos
                Repeater {
                    model: project.frames
                    Rectangle {
                        x: sheet.starts[index] * sheet.unit
                        y: 72
                        width: modelData.hold * sheet.unit
                        height: 26
                        radius: 4
                        color: index === sheet.selected ? Theme.accent : "#2C3B58"
                        border.color: "#55FFFFFF"
                        Text { anchors.centerIn: parent; text: index + 1; color: "white"; font.pixelSize: 11 }
                        MouseArea { anchors.fill: parent; onClicked: sheet.selectPhoto(index) }
                    }
                }
                // slot of the next photo
                Rectangle {
                    x: project.totalFrames * sheet.unit; y: 72
                    width: sheet.unit * 2; height: 26; radius: 4
                    color: "transparent"; border.color: "#FF6B6B"; border.width: 2
                    visible: !sheet.playing
                    Text { anchors.centerIn: parent; text: "+"; color: "#FF6B6B"; font.pixelSize: 14; font.weight: Font.Bold }
                }

                // cursor
                Rectangle {
                    x: sheet.cursorFrame * sheet.unit
                    y: 12; width: sheet.unit; height: parent.height - 12
                    color: "#26FF6B6B"; border.color: "#FF6B6B"
                }
            }
        }
    }
}
