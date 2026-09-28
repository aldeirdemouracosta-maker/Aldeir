import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import StopMotionStudio

// "IA Local": clean rigs/wires, replace green-screen backgrounds and upscale
// photos with Real-ESRGAN on the GPU. Originals are always kept.
Item {
    id: page

    property string tool: "limpeza"        // limpeza | fundo | upscale
    property int current: Math.max(0, project.frameCount - 1)
    property var selection: ({})           // index → true
    readonly property var selectedList: Object.keys(selection).map(Number).sort((a, b) => a - b)
    property bool showBefore: false

    // cleanup
    property bool usePlate: project.cleanPlateUrl.toString() !== ""
    property int brush: 28
    property bool eraser: false
    property int feather: 6
    property bool maskEmpty: true
    readonly property string maskPath: project.projectPath + "/export/.mascara.png"

    // chroma
    property color keyColor: "#14B43C"
    property real tolerance: 0.18
    property real softness: 0.10
    property bool spill: true
    property url background: ""
    property bool picking: false

    property int upscaleFactor: 2

    function toggleSelect(i) {
        const s = Object.assign({}, selection)
        if (s[i]) delete s[i]; else s[i] = true
        selection = s
    }
    function selectAll() { const s = {}; for (let i = 0; i < project.frameCount; ++i) s[i] = true; selection = s }
    function targets(all) { return all ? (selectedList.length ? selectedList : [current]) : [current] }
    function saveMask() {
        if (maskEmpty) { frameTools.clearPreview(); return false }
        return maskCanvas.save(maskPath)
    }
    function preview() {
        if (tool === "limpeza") { if (saveMask()) frameTools.previewCleanup(current, maskPath, usePlate, feather) }
        else if (tool === "fundo") frameTools.previewChroma(current, keyColor, tolerance, softness, spill, background)
    }
    function apply(all) {
        const list = targets(all)
        if (tool === "limpeza") { if (saveMask()) frameTools.applyCleanup(list, maskPath, usePlate, feather) }
        else if (tool === "fundo") frameTools.applyChroma(list, keyColor, tolerance, softness, spill, background)
        else frameTools.upscale(list, upscaleFactor)
    }

    onCurrentChanged: frameTools.clearPreview()
    onToolChanged: { frameTools.clearPreview(); picking = false }

    FileDialog {
        id: plateDialog
        title: "Placa limpa (cenário sem boneco e sem suportes)"
        nameFilters: ["Imagens (*.png *.jpg *.jpeg *.webp)"]
        onAccepted: project.setCleanPlateFromUrl(selectedFile)
    }
    FileDialog {
        id: bgDialog
        title: "Imagem de fundo (cenário)"
        nameFilters: ["Imagens (*.png *.jpg *.jpeg *.webp)"]
        onAccepted: { page.background = selectedFile; page.preview() }
    }

    component SectionTitle: Text { color: Theme.textDim; font.pixelSize: 12; Layout.topMargin: 4 }
    component LabeledSlider: ColumnLayout {
        property alias from: sl.from
        property alias to: sl.to
        property alias value: sl.value
        property alias stepSize: sl.stepSize
        property string label
        property string valueText
        signal moved(real value)
        spacing: 0
        Layout.fillWidth: true
        Text { text: parent.label + ": " + parent.valueText; color: Theme.textDim; font.pixelSize: 12 }
        Slider { id: sl; Layout.fillWidth: true; focusPolicy: Qt.NoFocus; onMoved: parent.moved(value) }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 10

        // ── toolbar ─────────────────────────────────────────────
        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            Text { text: "IA Local"; color: Theme.text; font.pixelSize: 20; font.weight: Font.DemiBold }
            Text { text: project.projectName ? "· " + project.projectName : ""; color: Theme.textDim; font.pixelSize: 16 }
            Item { Layout.preferredWidth: 10 }
            Repeater {
                model: [{ id: "limpeza", t: "Limpar suportes", i: "scenes" },
                        { id: "fundo", t: "Trocar fundo", i: "image" },
                        { id: "upscale", t: "Upscale IA", i: "chip" }]
                IconButton { iconName: modelData.i; text: modelData.t; highlighted: page.tool === modelData.id; onClicked: page.tool = modelData.id }
            }
            Item { Layout.fillWidth: true }
            Text {
                text: page.selectedList.length ? page.selectedList.length + " selecionado(s)" : "Quadro " + (page.current + 1)
                color: Theme.textDim; font.pixelSize: 14
            }
            IconButton { text: "Todos"; onClicked: page.selectAll() }
            IconButton { text: "Nenhum"; enabled: page.selectedList.length > 0; onClicked: page.selection = {} }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 12

            // ── editor ─────────────────────────────────────────
            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                radius: 10
                color: "black"
                clip: true

                Image {
                    id: photo
                    anchors.fill: parent
                    anchors.margins: 8
                    fillMode: Image.PreserveAspectFit
                    source: project.frameCount ? project.frameUrl(page.current) : ""
                    sourceSize.width: 1920
                    asynchronous: true
                }
                Image {
                    anchors.fill: photo
                    fillMode: Image.PreserveAspectFit
                    source: frameTools.previewUrl
                    visible: frameTools.previewUrl.toString() !== "" && !page.showBefore
                    sourceSize.width: 1920
                    cache: false
                }

                // Painted area of the photo (mask and eyedropper coordinates).
                Item {
                    id: paintArea
                    x: photo.x + (photo.width - photo.paintedWidth) / 2
                    y: photo.y + (photo.height - photo.paintedHeight) / 2
                    width: photo.paintedWidth
                    height: photo.paintedHeight

                    Canvas {
                        id: maskCanvas
                        anchors.fill: parent
                        visible: page.tool === "limpeza"
                        opacity: frameTools.previewUrl.toString() !== "" && !page.showBefore ? 0.25 : 1
                        property point last
                        property point cur
                        property bool clearing: false
                        onWidthChanged: { clearing = true; page.maskEmpty = true; requestPaint() }
                        onHeightChanged: { clearing = true; page.maskEmpty = true; requestPaint() }
                        onPaint: {
                            const c = getContext("2d")
                            if (clearing) { c.reset(); clearing = false; return }
                            c.globalCompositeOperation = page.eraser ? "destination-out" : "source-over"
                            c.strokeStyle = "rgba(255,70,70,0.55)"
                            c.lineCap = "round"; c.lineJoin = "round"
                            c.lineWidth = page.brush
                            c.beginPath(); c.moveTo(last.x, last.y); c.lineTo(cur.x, cur.y); c.stroke()
                        }
                        MouseArea {
                            anchors.fill: parent
                            enabled: page.tool === "limpeza"
                            cursorShape: Qt.CrossCursor
                            onPressed: (m) => { maskCanvas.last = Qt.point(m.x, m.y); maskCanvas.cur = Qt.point(m.x + 0.1, m.y); maskCanvas.requestPaint(); if (!page.eraser) page.maskEmpty = false }
                            onPositionChanged: (m) => { maskCanvas.last = maskCanvas.cur; maskCanvas.cur = Qt.point(m.x, m.y); maskCanvas.requestPaint() }
                            onReleased: frameTools.clearPreview()
                        }
                    }

                    MouseArea {
                        anchors.fill: parent
                        enabled: page.tool === "fundo" && page.picking
                        cursorShape: Qt.CrossCursor
                        onClicked: (m) => {
                            page.keyColor = frameTools.colorAt(page.current, m.x / width, m.y / height)
                            page.picking = false
                            page.preview()
                        }
                    }
                }

                Row {
                    anchors.left: parent.left; anchors.top: parent.top; anchors.margins: 12
                    spacing: 8
                    visible: frameTools.previewUrl.toString() !== ""
                    IconButton { text: "Antes"; highlighted: page.showBefore; onClicked: page.showBefore = true }
                    IconButton { text: "Depois"; highlighted: !page.showBefore; onClicked: page.showBefore = false }
                }
                Rectangle {
                    visible: page.picking
                    anchors.horizontalCenter: parent.horizontalCenter; anchors.top: parent.top; anchors.topMargin: 12
                    radius: 8; color: "#E6131D30"; width: pickText.implicitWidth + 24; height: 34
                    Text { id: pickText; anchors.centerIn: parent; text: "Clique no fundo verde/azul para escolher a cor"; color: Theme.text; font.pixelSize: 14 }
                }
                Column {
                    anchors.centerIn: parent
                    visible: project.frameCount === 0
                    spacing: 8
                    Image { source: Theme.icon("chip"); width: 56; height: 56; sourceSize: Qt.size(112, 112); anchors.horizontalCenter: parent.horizontalCenter; opacity: 0.6 }
                    Text { text: "Capture ou importe fotos para usar as ferramentas de IA"; color: Theme.text; font.pixelSize: 16 }
                }
            }

            // ── tool panel ─────────────────────────────────────
            Rectangle {
                Layout.preferredWidth: 320
                Layout.fillWidth: false
                Layout.fillHeight: true
                radius: 10
                color: Theme.panel
                border.color: "#1FFFFFFF"

                Flickable {
                    anchors.fill: parent
                    anchors.margins: 14
                    contentHeight: panel.implicitHeight
                    clip: true

                    ColumnLayout {
                        id: panel
                        width: parent.width
                        spacing: 8

                        // ── cleanup
                        ColumnLayout {
                            visible: page.tool === "limpeza"
                            Layout.fillWidth: true
                            spacing: 8
                            Text { text: "Limpar suportes e fios"; color: Theme.text; font.pixelSize: 17; font.weight: Font.DemiBold }
                            Text {
                                Layout.fillWidth: true; wrapMode: Text.WordWrap; color: Theme.textDim; font.pixelSize: 12
                                text: "Pinte sobre o suporte, arame ou fio. Com uma placa limpa (foto do cenário sem boneco) a área é trocada pelo cenário real; sem placa, é preenchida a partir dos arredores."
                            }
                            SectionTitle { text: "Placa limpa" }
                            RowLayout {
                                Layout.fillWidth: true
                                Rectangle {
                                    width: 96; height: 64; radius: 6; color: "#1A2438"; clip: true
                                    Image { anchors.fill: parent; source: project.cleanPlateUrl; fillMode: Image.PreserveAspectCrop; sourceSize.width: 200; cache: false }
                                    Text { anchors.centerIn: parent; visible: project.cleanPlateUrl.toString() === ""; text: "nenhuma"; color: Theme.textDim; font.pixelSize: 12 }
                                }
                                ColumnLayout {
                                    spacing: 4
                                    IconButton { text: "Usar quadro atual"; implicitHeight: 30; enabled: project.frameCount > 0; onClicked: project.setCleanPlateFromFrame(page.current) }
                                    IconButton { text: "Importar…"; implicitHeight: 30; onClicked: plateDialog.open() }
                                }
                            }
                            IconButton {
                                iconName: "camera"; implicitHeight: 30
                                text: project.capturingCleanPlate ? "Próxima foto vira a placa ✓" : "Capturar placa na próxima foto"
                                highlighted: project.capturingCleanPlate
                                tip: "A próxima foto tirada na Captura será salva como placa limpa (não entra na animação)"
                                onClicked: project.captureCleanPlateNext(!project.capturingCleanPlate)
                            }
                            SectionTitle { text: "Modo" }
                            RowLayout {
                                IconButton { text: "Com placa limpa"; highlighted: page.usePlate; enabled: project.cleanPlateUrl.toString() !== ""; onClicked: { page.usePlate = true; frameTools.clearPreview() } }
                                IconButton { text: "Preencher"; highlighted: !page.usePlate; onClicked: { page.usePlate = false; frameTools.clearPreview() } }
                            }
                            LabeledSlider {
                                label: "Pincel"; valueText: page.brush + " px"
                                from: 4; to: 120; stepSize: 1; value: page.brush
                                onMoved: (v) => page.brush = v
                            }
                            LabeledSlider {
                                visible: page.usePlate
                                label: "Suavizar borda"; valueText: page.feather + " px"
                                from: 0; to: 30; stepSize: 1; value: page.feather
                                onMoved: (v) => page.feather = v
                            }
                            RowLayout {
                                IconButton { text: page.eraser ? "Borracha" : "Pincel"; iconName: page.eraser ? "minus" : "plus"; highlighted: page.eraser; onClicked: page.eraser = !page.eraser }
                                IconButton { iconName: "trash"; text: "Limpar máscara"; onClicked: { maskCanvas.clearing = true; maskCanvas.requestPaint(); page.maskEmpty = true; frameTools.clearPreview() } }
                            }
                        }

                        // ── chroma key
                        ColumnLayout {
                            visible: page.tool === "fundo"
                            Layout.fillWidth: true
                            spacing: 8
                            Text { text: "Trocar fundo (chroma key)"; color: Theme.text; font.pixelSize: 17; font.weight: Font.DemiBold }
                            Text {
                                Layout.fillWidth: true; wrapMode: Text.WordWrap; color: Theme.textDim; font.pixelSize: 12
                                text: "Fotografe os bonecos contra um fundo verde ou azul liso e troque pelo cenário que quiser."
                            }
                            SectionTitle { text: "Cor do fundo" }
                            RowLayout {
                                spacing: 6
                                Repeater {
                                    model: ["#14B43C", "#1E5AE6"]
                                    Rectangle {
                                        width: 32; height: 32; radius: 16; color: modelData
                                        border.width: Qt.colorEqual(page.keyColor, modelData) ? 3 : 1
                                        border.color: Qt.colorEqual(page.keyColor, modelData) ? "white" : "#55FFFFFF"
                                        MouseArea { anchors.fill: parent; onClicked: { page.keyColor = modelData; page.preview() } }
                                    }
                                }
                                Rectangle { width: 32; height: 32; radius: 6; color: page.keyColor; border.color: "#55FFFFFF" }
                                IconButton { iconName: "search"; text: "Conta-gotas"; highlighted: page.picking; enabled: project.frameCount > 0; onClicked: page.picking = !page.picking }
                            }
                            LabeledSlider {
                                label: "Tolerância"; valueText: Math.round(page.tolerance * 100)
                                from: 0.02; to: 0.6; value: page.tolerance
                                onMoved: (v) => page.tolerance = v
                            }
                            LabeledSlider {
                                label: "Suavidade da borda"; valueText: Math.round(page.softness * 100)
                                from: 0.01; to: 0.4; value: page.softness
                                onMoved: (v) => page.softness = v
                            }
                            RowLayout {
                                Switch { checked: page.spill; onToggled: page.spill = checked; focusPolicy: Qt.NoFocus }
                                Text { text: "Remover reflexo verde/azul no boneco"; color: Theme.text; font.pixelSize: 13; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                            }
                            SectionTitle { text: "Novo fundo" }
                            RowLayout {
                                Rectangle {
                                    width: 96; height: 64; radius: 6; clip: true
                                    color: "#1A2438"
                                    Image { anchors.fill: parent; source: page.background; fillMode: Image.PreserveAspectCrop; sourceSize.width: 200 }
                                    Text { anchors.centerIn: parent; visible: page.background.toString() === ""; text: "transparente"; color: Theme.textDim; font.pixelSize: 12 }
                                }
                                ColumnLayout {
                                    spacing: 4
                                    IconButton { text: "Escolher cenário…"; implicitHeight: 30; onClicked: bgDialog.open() }
                                    IconButton { text: "Transparente"; implicitHeight: 30; onClicked: { page.background = ""; page.preview() } }
                                }
                            }
                        }

                        // ── upscale
                        ColumnLayout {
                            visible: page.tool === "upscale"
                            Layout.fillWidth: true
                            spacing: 8
                            Text { text: "Upscale com IA"; color: Theme.text; font.pixelSize: 17; font.weight: Font.DemiBold }
                            Text {
                                Layout.fillWidth: true; wrapMode: Text.WordWrap; color: Theme.textDim; font.pixelSize: 12
                                text: frameTools.upscalerAvailable
                                      ? "Real-ESRGAN via Vulkan, na placa de vídeo (RX 580). Aumenta a resolução recriando detalhes de textura — útil para fotos de webcam ou para exportar em 4K."
                                      : "Real-ESRGAN não encontrado. Instale com:\nscripts/instalar-realesrgan.sh"
                            }
                            SectionTitle { text: "Fator" }
                            RowLayout {
                                IconButton { text: "2×"; highlighted: page.upscaleFactor === 2; onClicked: page.upscaleFactor = 2 }
                                IconButton { text: "4× (foto)"; highlighted: page.upscaleFactor === 4; onClicked: page.upscaleFactor = 4 }
                            }
                            Text {
                                Layout.fillWidth: true; wrapMode: Text.WordWrap; color: Theme.textDim; font.pixelSize: 12
                                text: "Resolução atual: " + project.resolutionText + ". Leva alguns segundos por foto na GPU."
                            }
                        }

                        // ── actions (shared)
                        Rectangle { Layout.fillWidth: true; height: 1; color: "#1FFFFFFF"; Layout.topMargin: 6 }
                        IconButton {
                            Layout.fillWidth: true
                            visible: page.tool !== "upscale"
                            iconName: "search"; text: "Prévia no quadro " + (page.current + 1)
                            enabled: project.frameCount > 0 && !frameTools.busy
                            onClicked: page.preview()
                        }
                        IconButton {
                            Layout.fillWidth: true
                            iconName: "plus"; text: "Aplicar no quadro " + (page.current + 1)
                            enabled: project.frameCount > 0 && !frameTools.busy && (page.tool !== "upscale" || frameTools.upscalerAvailable)
                            onClicked: page.apply(false)
                        }
                        IconButton {
                            Layout.fillWidth: true
                            highlighted: true
                            iconName: "plus"; text: page.selectedList.length ? "Aplicar nos " + page.selectedList.length + " selecionados" : "Aplicar (selecione quadros)"
                            enabled: page.selectedList.length > 0 && !frameTools.busy && (page.tool !== "upscale" || frameTools.upscalerAvailable)
                            onClicked: page.apply(true)
                        }
                        IconButton {
                            Layout.fillWidth: true
                            iconName: "undo"; text: "Restaurar original"
                            enabled: !frameTools.busy && project.frameCount > 0
                            onClicked: frameTools.restore(page.targets(true))
                        }
                        ProgressBar { Layout.fillWidth: true; value: frameTools.progress; visible: frameTools.busy }
                        Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; text: frameTools.status; color: Theme.text; font.pixelSize: 12 }
                    }
                }
            }
        }

        // ── filmstrip with selection ────────────────────────────
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 104
            radius: 10
            color: Theme.panel
            border.color: "#1FFFFFFF"
            ListView {
                id: strip
                anchors.fill: parent
                anchors.margins: 8
                orientation: ListView.Horizontal
                spacing: 6
                clip: true
                model: project.frames
                currentIndex: page.current
                delegate: Rectangle {
                    width: 118; height: strip.height; radius: 6
                    color: "#0E1422"
                    border.width: 2
                    border.color: index === page.current ? Theme.accent : "transparent"
                    Image { anchors.fill: parent; anchors.margins: 3; source: modelData.url; sourceSize.width: 220; fillMode: Image.PreserveAspectCrop; asynchronous: true }
                    Rectangle {
                        anchors.left: parent.left; anchors.bottom: parent.bottom; anchors.margins: 5
                        radius: 4; color: "#B3000000"; width: n.implicitWidth + 10; height: 18
                        Text { id: n; anchors.centerIn: parent; text: (index + 1) + (modelData.edited ? " ✎" : ""); color: "white"; font.pixelSize: 11 }
                    }
                    MouseArea { anchors.fill: parent; onClicked: page.current = index }
                    Rectangle {
                        anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 5
                        width: 22; height: 22; radius: 5
                        color: page.selection[index] ? Theme.accent : "#99000000"
                        border.color: "white"
                        Text { anchors.centerIn: parent; text: page.selection[index] ? "✓" : ""; color: "white"; font.pixelSize: 14; font.weight: Font.Bold }
                        MouseArea { anchors.fill: parent; anchors.margins: -4; onClicked: page.toggleSelect(index) }
                    }
                }
            }
        }
    }
}
