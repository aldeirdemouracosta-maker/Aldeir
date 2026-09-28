import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import StopMotionStudio

// Character library: replacement mouths (A–H, X) for lip sync, and the
// digital mouth placement for the current project.
Item {
    id: page

    property string selectedPath: project.characterPath || (characters.characters.length ? characters.characters[0].path : "")
    readonly property var selected: characters.characters.find(c => c.path === selectedPath)
    property string targetShape: ""
    property int previewIndex: Math.max(0, project.frameCount - 1)
    property string toast

    readonly property var starts: {
        let acc = 0, list = []
        for (const f of project.frames) { list.push(acc); acc += f.hold }
        return list
    }

    function notify(t) { toast = t; toastTimer.restart() }
    Timer { id: toastTimer; interval: 4000; onTriggered: page.toast = "" }

    function applyMouths() {
        if (!project.characterPath) { notify("Escolha o personagem deste projeto primeiro."); return }
        if (!audioTrack.mouths.length) { notify("Rode a sincronia labial no dope sheet da Captura primeiro."); return }
        const shapes = {}, indices = []
        for (let i = 0; i < project.frameCount; ++i) {
            shapes[i] = audioTrack.mouthAt(starts[i])
            indices.push(i)
        }
        frameTools.applyMouths(indices, shapes, project.characterPath, project.mouthCenter.x, project.mouthCenter.y, project.mouthWidth)
    }

    Connections {
        target: frameTools
        function onFinished(ok, message) { page.notify(message) }
    }

    FileDialog {
        id: mouthDialog
        title: "Imagem da boca " + page.targetShape + " (PNG com fundo transparente é o ideal)"
        nameFilters: ["Imagens (*.png *.webp *.jpg *.jpeg)"]
        onAccepted: characters.setMouth(page.selectedPath, page.targetShape, selectedFile)
    }
    FileDialog {
        id: refDialog
        title: "Foto de referência do personagem"
        nameFilters: ["Imagens (*.png *.jpg *.jpeg *.webp)"]
        onAccepted: characters.setReference(page.selectedPath, selectedFile)
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 10

        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            Text { text: "Personagens"; color: Theme.text; font.pixelSize: 20; font.weight: Font.DemiBold }
            Text { text: "bocas para sincronia labial"; color: Theme.textDim; font.pixelSize: 15 }
            Item { Layout.fillWidth: true }
            IconButton { iconName: "plus"; text: "Novo personagem"; onClicked: page.selectedPath = characters.createCharacter("Novo personagem") }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 12

            // ── list
            Rectangle {
                Layout.preferredWidth: 230
                Layout.fillWidth: false
                Layout.fillHeight: true
                radius: 10; color: Theme.panel; border.color: "#1FFFFFFF"
                ListView {
                    anchors.fill: parent; anchors.margins: 8
                    spacing: 6; clip: true
                    model: characters.characters
                    delegate: Rectangle {
                        width: ListView.view.width; height: 72; radius: 8
                        color: modelData.path === page.selectedPath ? Theme.accentSoft : "#10FFFFFF"
                        border.color: modelData.path === page.selectedPath ? Theme.accent : "transparent"
                        RowLayout {
                            anchors.fill: parent; anchors.margins: 8; spacing: 10
                            Rectangle {
                                Layout.preferredWidth: 56; Layout.preferredHeight: 56; radius: 6; color: "#F4E9D3"; clip: true
                                Image { anchors.fill: parent; anchors.margins: 2; source: modelData.thumbnail; fillMode: Image.PreserveAspectFit; sourceSize.width: 120 }
                            }
                            ColumnLayout {
                                spacing: 2; Layout.fillWidth: true
                                Text { text: modelData.name; color: Theme.text; font.pixelSize: 14; font.weight: Font.DemiBold; elide: Text.ElideRight; Layout.fillWidth: true }
                                Text { text: modelData.mouthCount + "/9 bocas"; color: Theme.textDim; font.pixelSize: 12 }
                                Text { visible: modelData.path === project.characterPath; text: "● neste projeto"; color: Theme.gpu; font.pixelSize: 12 }
                            }
                        }
                        MouseArea { anchors.fill: parent; onClicked: page.selectedPath = modelData.path }
                    }
                }
            }

            // ── mouths of the selected character
            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                radius: 10; color: Theme.panel; border.color: "#1FFFFFFF"
                visible: page.selected !== undefined

                ColumnLayout {
                    anchors.fill: parent; anchors.margins: 14; spacing: 10
                    RowLayout {
                        Layout.fillWidth: true
                        TextField {
                            Layout.preferredWidth: 260
                            text: page.selected ? page.selected.name : ""
                            font.pixelSize: 16
                            onEditingFinished: if (page.selected && text !== page.selected.name) characters.renameCharacter(page.selectedPath, text)
                        }
                        IconButton { iconName: "image"; text: "Foto de referência"; onClicked: refDialog.open() }
                        Item { Layout.fillWidth: true }
                        IconButton {
                            iconName: "user"
                            text: project.characterPath === page.selectedPath ? "Em uso neste projeto" : "Usar neste projeto"
                            highlighted: project.characterPath === page.selectedPath
                            onClicked: project.characterPath = page.selectedPath
                        }
                        IconButton { iconName: "trash"; tip: "Mover personagem para a lixeira"; onClicked: { characters.removeCharacter(page.selectedPath); page.selectedPath = "" } }
                    }
                    Text {
                        Layout.fillWidth: true; wrapMode: Text.WordWrap; color: Theme.textDim; font.pixelSize: 12
                        text: "Fotografe cada boca de substituição do boneco (ou desenhe) e importe como PNG — de preferência com fundo transparente. A Captura mostra qual boca colocar a cada foto; a boca digital pode aplicá-las automaticamente."
                    }
                    GridLayout {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        columns: 3
                        rowSpacing: 8; columnSpacing: 8
                        Repeater {
                            model: characters.shapes
                            Rectangle {
                                Layout.fillWidth: true; Layout.fillHeight: true
                                Layout.minimumHeight: 110
                                radius: 8; color: "#10FFFFFF"; border.color: "#22FFFFFF"
                                readonly property url mouth: page.selected ? page.selected.mouths[modelData] : ""
                                RowLayout {
                                    anchors.fill: parent; anchors.margins: 8; spacing: 10
                                    Rectangle {
                                        Layout.preferredWidth: Math.min(parent.width * 0.5, parent.height * 1.6)
                                        Layout.fillWidth: false
                                        Layout.fillHeight: true
                                        radius: 6; color: "#F4E9D3"; clip: true
                                        Image { anchors.fill: parent; anchors.margins: 4; source: parent.parent.parent.mouth; fillMode: Image.PreserveAspectFit; sourceSize.width: 240 }
                                        Text { anchors.centerIn: parent; visible: parent.parent.parent.mouth.toString() === ""; text: "sem imagem"; color: "#8A7A66"; font.pixelSize: 11 }
                                    }
                                    ColumnLayout {
                                        spacing: 4; Layout.fillWidth: true; Layout.minimumWidth: 90
                                        Text { text: modelData; color: Theme.text; font.pixelSize: 22; font.weight: Font.Black }
                                        Text { text: audioTrack.mouthDescription(modelData); color: Theme.textDim; font.pixelSize: 12; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                                        RowLayout {
                                            IconButton { text: "Trocar…"; implicitHeight: 28; onClicked: { page.targetShape = modelData; mouthDialog.open() } }
                                            IconButton { iconName: "trash"; implicitHeight: 28; implicitWidth: 28; visible: parent.parent.parent.parent.mouth.toString() !== ""; onClicked: characters.clearMouth(page.selectedPath, modelData) }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // ── digital mouth for the current project
            Rectangle {
                Layout.preferredWidth: 360
                Layout.fillWidth: false
                Layout.fillHeight: true
                radius: 10; color: Theme.panel; border.color: "#1FFFFFFF"

                ColumnLayout {
                    anchors.fill: parent; anchors.margins: 14; spacing: 8
                    Text { text: "Boca digital neste projeto"; color: Theme.text; font.pixelSize: 16; font.weight: Font.DemiBold }
                    Text {
                        Layout.fillWidth: true; wrapMode: Text.WordWrap; color: Theme.textDim; font.pixelSize: 12
                        text: "Para bonecos sem boca trocável: clique no rosto para posicionar a boca e ajuste o tamanho. As bocas seguem a sincronia labial do dope sheet."
                    }
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: width * 0.62
                        radius: 6; color: "black"; clip: true
                        Image {
                            id: facePhoto
                            anchors.fill: parent
                            fillMode: Image.PreserveAspectFit
                            source: project.frameCount ? project.frameUrl(page.previewIndex) : ""
                            sourceSize.width: 720
                        }
                        Item {
                            id: faceArea
                            x: (facePhoto.width - facePhoto.paintedWidth) / 2; y: (facePhoto.height - facePhoto.paintedHeight) / 2
                            width: facePhoto.paintedWidth; height: facePhoto.paintedHeight
                            Image {
                                readonly property string shape: audioTrack.mouthAt(page.starts[page.previewIndex] || 0) || "D"
                                source: project.characterPath ? characters.mouthUrl(project.characterPath, shape) : ""
                                width: faceArea.width * project.mouthWidth
                                height: implicitHeight > 0 ? width * implicitHeight / implicitWidth : width / 2
                                x: project.mouthCenter.x * faceArea.width - width / 2
                                y: project.mouthCenter.y * faceArea.height - height / 2
                                fillMode: Image.PreserveAspectFit
                            }
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.CrossCursor
                                enabled: project.characterPath !== ""
                                onPressed: (m) => project.mouthCenter = Qt.point(m.x / width, m.y / height)
                                onPositionChanged: (m) => project.mouthCenter = Qt.point(m.x / width, m.y / height)
                            }
                        }
                    }
                    RowLayout {
                        Text { text: "Quadro"; color: Theme.textDim; font.pixelSize: 12 }
                        Slider {
                            Layout.fillWidth: true; from: 0; to: Math.max(0, project.frameCount - 1); stepSize: 1
                            value: page.previewIndex; onMoved: page.previewIndex = value; focusPolicy: Qt.NoFocus
                        }
                        Text { text: (page.previewIndex + 1) + " · boca " + (audioTrack.mouthAt(page.starts[page.previewIndex] || 0) || "—"); color: Theme.text; font.pixelSize: 12 }
                    }
                    RowLayout {
                        Text { text: "Tamanho"; color: Theme.textDim; font.pixelSize: 12 }
                        Slider {
                            Layout.fillWidth: true; from: 0.03; to: 0.4
                            value: project.mouthWidth; onMoved: project.mouthWidth = value; focusPolicy: Qt.NoFocus
                        }
                    }
                    Text {
                        Layout.fillWidth: true; wrapMode: Text.WordWrap; font.pixelSize: 12
                        color: audioTrack.mouths.length ? Theme.gpu : Theme.warn
                        text: !project.characterPath ? "Escolha um personagem e clique em \"Usar neste projeto\"."
                              : audioTrack.mouths.length ? "Sincronia labial pronta: " + audioTrack.mouths.length + " quadros de áudio."
                              : "Falta a sincronia labial: importe o áudio e rode \"Sincronia labial\" no dope sheet da Captura."
                    }
                    IconButton {
                        Layout.fillWidth: true
                        highlighted: true
                        iconName: "user"; text: frameTools.busy ? "Aplicando…" : "Aplicar bocas em todos os quadros"
                        enabled: !frameTools.busy && project.frameCount > 0 && project.characterPath !== "" && audioTrack.mouths.length > 0
                        onClicked: page.applyMouths()
                    }
                    ProgressBar { Layout.fillWidth: true; value: frameTools.progress; visible: frameTools.busy }
                    Text {
                        Layout.fillWidth: true; wrapMode: Text.WordWrap; color: Theme.textDim; font.pixelSize: 11
                        text: "Os originais ficam guardados; use \"Restaurar original\" na IA Local para desfazer."
                    }
                    Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; text: page.toast; color: Theme.text; font.pixelSize: 12 }
                    Item { Layout.fillHeight: true }
                }
            }
        }
    }
}
