import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import StopMotionStudio

// Scenery library: generate stop-motion style backgrounds with local AI
// (stable-diffusion.cpp on the RX 580) or import photos, then send them to
// the timeline or use them as the new background in IA Local.
Item {
    id: page
    signal useAsBackground(url image)

    property string style: "feltro"
    property string format: timeline.format === "vertical" ? "9:16" : timeline.format === "quadrado" ? "1:1" : "16:9"
    property int steps: 20
    property bool randomSeed: true
    property int seed: 42
    property var selected: scenery.items.length ? scenery.items[0] : undefined
    property string toast

    function notify(t) { toast = t; toastTimer.restart() }
    Timer { id: toastTimer; interval: 4000; onTriggered: page.toast = "" }

    Connections {
        target: scenery
        function onGenerated(image) { page.selected = scenery.items[0] }
        function onFailed(message) { page.notify(message) }
    }

    FileDialog {
        id: importDialog
        title: "Importar cenários (fotos, pinturas)"
        fileMode: FileDialog.OpenFiles
        nameFilters: ["Imagens (*.png *.jpg *.jpeg *.webp)"]
        onAccepted: page.notify(scenery.importImages(selectedFiles) + " cenário(s) importado(s)")
    }

    RowLayout {
        anchors.fill: parent
        spacing: 12

        // ── generator ─────────────────────────────────────────
        Rectangle {
            Layout.preferredWidth: 360
            Layout.fillWidth: false
            Layout.fillHeight: true
            radius: 10; color: Theme.panel; border.color: "#1FFFFFFF"

            Flickable {
                anchors.fill: parent; anchors.margins: 14
                contentHeight: gen.implicitHeight; clip: true
                ColumnLayout {
                    id: gen
                    width: parent.width
                    spacing: 10
                    Text { text: "Cenários"; color: Theme.text; font.pixelSize: 20; font.weight: Font.DemiBold }
                    Text {
                        Layout.fillWidth: true; wrapMode: Text.WordWrap; color: Theme.textDim; font.pixelSize: 12
                        text: scenery.generatorAvailable
                              ? "Descreva o cenário (de preferência em inglês) e escolha um estilo. A imagem é gerada no seu computador pela RX 580."
                              : "Geração por IA não instalada: rode scripts/instalar-cenarios.sh. Você ainda pode importar fotos e pinturas."
                    }
                    TextArea {
                        id: promptField
                        Layout.fillWidth: true
                        Layout.preferredHeight: 90
                        wrapMode: TextEdit.Wrap
                        placeholderText: "a cozy little kitchen with a round window, morning light"
                        color: Theme.text
                        background: Rectangle { radius: 6; color: "#1C2740"; border.color: Theme.panelBorder }
                    }
                    Text { text: "Estilo"; color: Theme.textDim; font.pixelSize: 12 }
                    Flow {
                        Layout.fillWidth: true
                        spacing: 6
                        Repeater {
                            model: scenery.styles
                            IconButton { text: modelData.label; implicitHeight: 32; highlighted: page.style === modelData.id; onClicked: page.style = modelData.id }
                        }
                    }
                    Text { text: "Formato"; color: Theme.textDim; font.pixelSize: 12 }
                    RowLayout {
                        Repeater {
                            model: ["16:9", "9:16", "1:1"]
                            IconButton { text: modelData; implicitHeight: 32; highlighted: page.format === modelData; onClicked: page.format = modelData }
                        }
                    }
                    Text { text: "Qualidade"; color: Theme.textDim; font.pixelSize: 12 }
                    RowLayout {
                        Repeater {
                            model: [{ s: 12, t: "Rascunho" }, { s: 20, t: "Boa" }, { s: 30, t: "Caprichada" }]
                            IconButton { text: modelData.t; implicitHeight: 32; highlighted: page.steps === modelData.s; onClicked: page.steps = modelData.s }
                        }
                    }
                    RowLayout {
                        Switch { checked: page.randomSeed; onToggled: page.randomSeed = checked; focusPolicy: Qt.NoFocus }
                        Text { text: page.randomSeed ? "Semente aleatória" : "Semente fixa"; color: Theme.text; font.pixelSize: 13 }
                        SpinBox {
                            visible: !page.randomSeed
                            from: 1; to: 2147483647; value: page.seed; editable: true
                            onValueModified: page.seed = value
                        }
                    }
                    IconButton {
                        Layout.fillWidth: true
                        highlighted: true
                        iconName: "chip"
                        text: scenery.busy ? "Gerando…" : "Gerar cenário"
                        enabled: scenery.generatorAvailable && !scenery.busy && promptField.text.trim().length > 0
                        onClicked: scenery.generate(promptField.text, page.style, page.format, page.steps, page.randomSeed ? -1 : page.seed)
                    }
                    IconButton { Layout.fillWidth: true; iconName: "stop"; text: "Cancelar"; visible: scenery.busy; onClicked: scenery.cancel() }
                    ProgressBar { Layout.fillWidth: true; value: scenery.progress; visible: scenery.busy }
                    Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; text: scenery.status; color: Theme.text; font.pixelSize: 12 }
                    Rectangle { Layout.fillWidth: true; height: 1; color: "#1FFFFFFF" }
                    IconButton { Layout.fillWidth: true; iconName: "import"; text: "Importar fotos de cenários"; onClicked: importDialog.open() }
                }
            }
        }

        // ── preview + gallery ────────────────────────────────
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 10

            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                radius: 10; color: "black"; clip: true
                Image {
                    anchors.fill: parent; anchors.margins: 8
                    fillMode: Image.PreserveAspectFit
                    source: page.selected ? page.selected.url : ""
                    sourceSize.width: 1600
                    asynchronous: true
                }
                Column {
                    anchors.centerIn: parent
                    visible: !page.selected
                    spacing: 8
                    Image { source: Theme.icon("image"); width: 56; height: 56; sourceSize: Qt.size(112, 112); anchors.horizontalCenter: parent.horizontalCenter; opacity: 0.6 }
                    Text { text: "Gere ou importe o primeiro cenário"; color: Theme.text; font.pixelSize: 16 }
                }
                Rectangle {
                    visible: page.selected !== undefined && page.selected.prompt !== ""
                    anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom; anchors.margins: 12
                    height: promptText.implicitHeight + 16; radius: 8; color: "#CC111A2B"
                    Text { id: promptText; anchors.fill: parent; anchors.margins: 8; wrapMode: Text.WordWrap; color: Theme.text; font.pixelSize: 12; text: page.selected ? "“" + page.selected.prompt + "” · " + page.selected.size : "" }
                }
                Rectangle {
                    visible: page.toast.length > 0
                    anchors.horizontalCenter: parent.horizontalCenter; anchors.top: parent.top; anchors.topMargin: 14
                    radius: 8; color: "#E6131D30"; border.color: Theme.panelBorder
                    width: Math.min(toastText.implicitWidth + 28, parent.width - 40); height: 34
                    Text { id: toastText; anchors.centerIn: parent; text: page.toast; color: Theme.text; font.pixelSize: 13 }
                }
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                IconButton {
                    iconName: "timeline"; text: "Adicionar à Timeline"; enabled: page.selected !== undefined
                    onClicked: { timeline.addMedia([page.selected.url], -1); page.notify("Cenário adicionado ao fim da Timeline.") }
                }
                IconButton {
                    iconName: "image"; text: "Usar como fundo (IA Local)"; enabled: page.selected !== undefined && project.frameCount > 0
                    tip: "Abre a IA Local em Trocar fundo com este cenário"
                    onClicked: page.useAsBackground(page.selected.url)
                }
                Item { Layout.fillWidth: true }
                IconButton { iconName: "folder"; tip: "Abrir a pasta de cenários"; onClicked: Qt.openUrlExternally("file://" + scenery.baseDir) }
                IconButton {
                    iconName: "trash"; tip: "Mover para a lixeira"; enabled: page.selected !== undefined
                    onClicked: { scenery.remove(page.selected.url); page.selected = scenery.items.length ? scenery.items[0] : undefined }
                }
            }
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 104
                radius: 10; color: Theme.panel; border.color: "#1FFFFFFF"
                ListView {
                    anchors.fill: parent; anchors.margins: 8
                    orientation: ListView.Horizontal; spacing: 6; clip: true
                    model: scenery.items
                    delegate: Rectangle {
                        width: 150; height: ListView.view.height; radius: 6; color: "#0E1422"
                        border.width: 2
                        border.color: page.selected && page.selected.url === modelData.url ? Theme.accent : "transparent"
                        Image { anchors.fill: parent; anchors.margins: 3; source: modelData.url; sourceSize.width: 300; fillMode: Image.PreserveAspectCrop; asynchronous: true }
                        Rectangle {
                            visible: modelData.generated
                            anchors.left: parent.left; anchors.top: parent.top; anchors.margins: 5
                            radius: 4; color: "#CC9B5CFF"; width: 22; height: 18
                            Text { anchors.centerIn: parent; text: "IA"; color: "white"; font.pixelSize: 10; font.weight: Font.Bold }
                        }
                        MouseArea { anchors.fill: parent; onClicked: page.selected = modelData }
                    }
                }
            }
        }
    }
}
