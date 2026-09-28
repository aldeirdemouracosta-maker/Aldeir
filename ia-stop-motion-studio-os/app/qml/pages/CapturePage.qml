import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import QtMultimedia
import StopMotionStudio

Item {
    id: page
    focus: true

    property bool autoPlay: false
    property int onionLayers: 1          // 0 = off, 1..3 previous frames
    property bool showGrid: true
    property bool showLastFrame: false   // toggle live view / last captured frame
    property bool cameraLocked: false
    property bool playing: false
    property int playIndex: 0
    property int playHoldLeft: 0
    property int selected: project.frameCount - 1
    property string toast

    readonly property bool hasCamera: mediaDevices.videoInputs.length > 0
    readonly property int count: project.frameCount

    Component.onCompleted: {
        project.attachImageCapture(imageCapture)
        if (autoPlay && count > 0)
            startPlayback()
        page.forceActiveFocus()
    }

    Connections {
        target: project
        function onFrameSaved(index) { page.selected = index; flash.restart() }
        function onErrorOccurred(message) { page.notify(message) }
    }

    function notify(text) { toast = text; toastTimer.restart() }

    function capture() {
        if (playing) stopPlayback()
        if (!hasCamera) { notify("Nenhuma câmera: conecte uma webcam/DSLR ou importe fotos."); return }
        if (!imageCapture.readyForCapture) { notify("Câmera ainda não está pronta."); return }
        imageCapture.capture()
    }

    function toggleLock() {
        cameraLocked = !cameraLocked
        const manual = cameraLocked
        let locked = []
        if (camera.isFocusModeSupported(manual ? Camera.FocusModeManual : Camera.FocusModeAuto)) {
            camera.focusMode = manual ? Camera.FocusModeManual : Camera.FocusModeAuto; locked.push("foco")
        }
        if (camera.isExposureModeSupported(manual ? Camera.ExposureManual : Camera.ExposureAuto)) {
            camera.exposureMode = manual ? Camera.ExposureManual : Camera.ExposureAuto; locked.push("exposição")
        }
        if (camera.isWhiteBalanceModeSupported(manual ? Camera.WhiteBalanceManual : Camera.WhiteBalanceAuto)) {
            camera.whiteBalanceMode = manual ? Camera.WhiteBalanceManual : Camera.WhiteBalanceAuto; locked.push("balanço de branco")
        }
        // Webcams usually only expose these through V4L2 controls.
        const v4l2 = cameraControl.setManual(camera.cameraDevice.id, manual)
        if (v4l2.length > 0) locked.push(v4l2)
        notify((manual ? "Câmera travada: " : "Câmera em automático: ")
               + (locked.length ? locked.join(", ") : "esta câmera não permite ajuste manual"))
    }

    function startPlayback() {
        if (count === 0) return
        playIndex = 0
        playHoldLeft = project.holdAt(0)
        playing = true
    }
    function stopPlayback() { playing = false }

    MediaDevices { id: mediaDevices }

    CaptureSession {
        camera: Camera {
            id: camera
            cameraDevice: cameraBox.currentIndex >= 0 ? mediaDevices.videoInputs[cameraBox.currentIndex] : mediaDevices.defaultVideoInput
            active: page.hasCamera
        }
        imageCapture: ImageCapture { id: imageCapture }
        videoOutput: videoOutput
    }

    Timer {
        id: playTimer
        interval: Math.round(1000 / project.fps)
        repeat: true
        running: page.playing
        onTriggered: {
            if (--page.playHoldLeft > 0) return
            page.playIndex = (page.playIndex + 1) % page.count
            page.playHoldLeft = project.holdAt(page.playIndex)
        }
    }
    Timer { id: toastTimer; interval: 3500; onTriggered: page.toast = "" }

    Shortcut { sequence: "Space"; onActivated: page.capture() }
    Shortcut { sequence: "Backspace"; onActivated: project.deleteLastFrame() }
    Shortcut { sequence: "O"; onActivated: page.onionLayers = (page.onionLayers + 1) % 4 }
    Shortcut { sequence: "G"; onActivated: page.showGrid = !page.showGrid }
    Shortcut { sequence: "L"; onActivated: page.showLastFrame = !page.showLastFrame }
    Shortcut { sequence: "P"; onActivated: page.playing ? page.stopPlayback() : page.startPlayback() }

    FileDialog {
        id: importDialog
        title: "Importar fotos"
        fileMode: FileDialog.OpenFiles
        nameFilters: ["Imagens (*.png *.jpg *.jpeg *.webp *.bmp)"]
        onAccepted: page.notify(project.importImages(selectedFiles) + " foto(s) importada(s)")
    }

    Dialog {
        id: newDialog
        title: "Novo projeto"
        modal: true
        anchors.centerIn: parent
        standardButtons: Dialog.Ok | Dialog.Cancel
        TextField { id: nameField; width: 320; placeholderText: "Nome do projeto"; text: "Novo Projeto" }
        onAccepted: project.newProject(nameField.text)
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 10

        // ── toolbar ─────────────────────────────────────────────
        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            Text {
                text: project.projectName || "Sem projeto"
                color: Theme.text; font.pixelSize: 20; font.weight: Font.DemiBold
                elide: Text.ElideRight
                Layout.maximumWidth: 260
            }
            IconButton { iconName: "plus"; tip: "Novo projeto"; onClicked: newDialog.open() }
            Item { Layout.preferredWidth: 8 }
            ComboBox {
                id: cameraBox
                Layout.preferredWidth: 230
                model: mediaDevices.videoInputs.map(d => d.description)
                displayText: page.hasCamera ? currentText : "Nenhuma câmera"
                enabled: page.hasCamera
                focusPolicy: Qt.NoFocus
            }
            IconButton {
                iconName: page.cameraLocked ? "lock" : "unlock"
                text: page.cameraLocked ? "Travada" : "Travar câmera"
                highlighted: page.cameraLocked
                enabled: page.hasCamera
                tip: "Trava foco, exposição e balanço de branco para evitar flicker entre quadros"
                onClicked: page.toggleLock()
            }
            IconButton { iconName: "import"; text: "Importar fotos"; onClicked: importDialog.open() }
            Item { Layout.fillWidth: true }
            IconButton {
                iconName: "onion"
                text: page.onionLayers ? "Onion " + page.onionLayers : "Onion"
                highlighted: page.onionLayers > 0
                tip: "Onion skin: mostra quadros anteriores transparentes (O)"
                onClicked: page.onionLayers = (page.onionLayers + 1) % 4
            }
            IconButton { iconName: "grid"; highlighted: page.showGrid; tip: "Grade (G)"; onClicked: page.showGrid = !page.showGrid }
            IconButton {
                iconName: "live"; text: page.showLastFrame ? "Último" : "Ao vivo"
                highlighted: page.showLastFrame
                tip: "Alterna entre câmera ao vivo e último quadro (L)"
                onClicked: page.showLastFrame = !page.showLastFrame
            }
            ComboBox {
                Layout.preferredWidth: 110
                model: [8, 12, 15, 24, 30]
                displayText: project.fps + " fps"
                currentIndex: model.indexOf(project.fps)
                onActivated: (i) => project.fps = model[i]
                focusPolicy: Qt.NoFocus
            }
        }

        // ── viewer + side controls ─────────────────────────────
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 12

            Rectangle {
                id: viewer
                Layout.fillWidth: true
                Layout.fillHeight: true
                radius: 10
                color: "black"
                clip: true

                VideoOutput {
                    id: videoOutput
                    anchors.fill: parent
                    fillMode: VideoOutput.PreserveAspectFit
                    visible: page.hasCamera && !page.playing
                }

                // Onion skin: previous frames stacked over the live view.
                Repeater {
                    model: page.playing ? 0 : (page.showLastFrame ? 1 : page.onionLayers)
                    Image {
                        anchors.fill: parent
                        fillMode: Image.PreserveAspectFit
                        source: project.frameUrl(page.count - 1 - index)
                        sourceSize.width: viewer.width
                        asynchronous: true
                        opacity: page.showLastFrame ? 1.0 : [0.45, 0.28, 0.16][index]
                        visible: page.count - 1 - index >= 0
                    }
                }

                Image {
                    anchors.fill: parent
                    fillMode: Image.PreserveAspectFit
                    visible: page.playing
                    source: page.playing ? project.frameUrl(page.playIndex) : ""
                    sourceSize.width: viewer.width
                    cache: true
                }

                Canvas {
                    anchors.fill: parent
                    visible: page.showGrid
                    onWidthChanged: requestPaint()
                    onHeightChanged: requestPaint()
                    onPaint: {
                        const c = getContext("2d")
                        c.reset()
                        c.strokeStyle = "rgba(255,255,255,0.28)"
                        c.lineWidth = 1
                        for (let i = 1; i < 3; ++i) {
                            c.beginPath(); c.moveTo(width * i / 3, 0); c.lineTo(width * i / 3, height); c.stroke()
                            c.beginPath(); c.moveTo(0, height * i / 3); c.lineTo(width, height * i / 3); c.stroke()
                        }
                    }
                }

                Column {
                    anchors.centerIn: parent
                    spacing: 10
                    visible: !page.hasCamera && page.count === 0
                    Image { source: Theme.icon("camera"); width: 64; height: 64; sourceSize: Qt.size(128, 128); anchors.horizontalCenter: parent.horizontalCenter; opacity: 0.6 }
                    Text { text: "Nenhuma câmera detectada"; color: Theme.text; font.pixelSize: 20; anchors.horizontalCenter: parent.horizontalCenter }
                    Text { text: "Conecte uma webcam ou câmera USB, ou importe fotos já tiradas."; color: Theme.textDim; font.pixelSize: 14; anchors.horizontalCenter: parent.horizontalCenter }
                }

                // status chips
                Row {
                    anchors.left: parent.left; anchors.top: parent.top; anchors.margins: 12
                    spacing: 8
                    Rectangle {
                        radius: 6; color: page.playing ? "#CC2E8BFF" : "#CCE0403A"
                        width: statusText.implicitWidth + 18; height: 26
                        Text {
                            id: statusText; anchors.centerIn: parent; color: "white"; font.pixelSize: 13; font.weight: Font.DemiBold
                            text: page.playing ? "▶ " + (page.playIndex + 1) + " / " + page.count
                                 : page.showLastFrame ? "ÚLTIMO QUADRO" : page.hasCamera ? "● AO VIVO" : "SEM CÂMERA"
                        }
                    }
                    Rectangle {
                        radius: 6; color: "#99000000"; width: fc.implicitWidth + 18; height: 26
                        Text { id: fc; anchors.centerIn: parent; color: "white"; font.pixelSize: 13; text: "Quadro " + (page.count + 1) + "  ·  " + project.durationText }
                    }
                }

                Rectangle { id: flashRect; anchors.fill: parent; color: "white"; opacity: 0 }
                SequentialAnimation {
                    id: flash
                    NumberAnimation { target: flashRect; property: "opacity"; to: 0.5; duration: 40 }
                    NumberAnimation { target: flashRect; property: "opacity"; to: 0; duration: 180 }
                }

                Rectangle {
                    visible: page.toast.length > 0
                    anchors.horizontalCenter: parent.horizontalCenter
                    anchors.bottom: parent.bottom; anchors.bottomMargin: 16
                    radius: 8; color: "#E6131D30"; border.color: Theme.panelBorder
                    width: Math.min(toastText.implicitWidth + 28, parent.width - 40); height: 36
                    Text { id: toastText; anchors.centerIn: parent; width: parent.width - 28; elide: Text.ElideRight; horizontalAlignment: Text.AlignHCenter; text: page.toast; color: Theme.text; font.pixelSize: 14 }
                }
            }

            ColumnLayout {
                Layout.preferredWidth: 170
                Layout.fillWidth: false
                Layout.fillHeight: true
                spacing: 10

                AbstractButton {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 130
                    focusPolicy: Qt.NoFocus
                    onClicked: page.capture()
                    background: Rectangle {
                        radius: 14
                        color: parent.down ? "#A82E2E" : parent.hovered ? "#E24848" : "#D23A3A"
                        border.color: "#FF8A8A"
                    }
                    contentItem: Column {
                        spacing: 6
                        topPadding: 18
                        Image { source: Theme.icon("camera"); width: 48; height: 48; sourceSize: Qt.size(96, 96); anchors.horizontalCenter: parent.horizontalCenter }
                        Text { text: "Capturar"; color: "white"; font.pixelSize: 18; font.weight: Font.Bold; anchors.horizontalCenter: parent.horizontalCenter }
                        Text { text: "Espaço"; color: "#FFD6D6"; font.pixelSize: 12; anchors.horizontalCenter: parent.horizontalCenter }
                    }
                }
                IconButton {
                    Layout.fillWidth: true
                    iconName: page.playing ? "stop" : "play"
                    text: page.playing ? "Parar (P)" : "Reproduzir (P)"
                    highlighted: page.playing
                    enabled: page.count > 0
                    onClicked: page.playing ? page.stopPlayback() : page.startPlayback()
                }
                IconButton {
                    Layout.fillWidth: true
                    iconName: "undo"; text: "Apagar último"
                    enabled: page.count > 0
                    tip: "Backspace — o quadro vai para a lixeira do projeto"
                    onClicked: project.deleteLastFrame()
                }
                Item { Layout.fillHeight: true }
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: holdCol.implicitHeight + 20
                    radius: 10; color: Theme.panel; border.color: "#1FFFFFFF"
                    visible: page.selected >= 0 && page.selected < page.count
                    ColumnLayout {
                        id: holdCol
                        anchors.fill: parent; anchors.margins: 10
                        Text { text: "Quadro " + (page.selected + 1); color: Theme.text; font.pixelSize: 14; font.weight: Font.DemiBold }
                        Text { text: "Exposição (dope sheet)"; color: Theme.textDim; font.pixelSize: 12 }
                        RowLayout {
                            IconButton { iconName: "minus"; implicitWidth: 34; implicitHeight: 34; onClicked: project.setHold(page.selected, project.holdAt(page.selected) - 1) }
                            Text {
                                Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter
                                text: (project.frames[page.selected] ? project.frames[page.selected].hold : 1) + "×"
                                color: Theme.text; font.pixelSize: 18
                            }
                            IconButton { iconName: "plus"; implicitWidth: 34; implicitHeight: 34; onClicked: project.setHold(page.selected, project.holdAt(page.selected) + 1) }
                        }
                        IconButton {
                            Layout.fillWidth: true; iconName: "trash"; text: "Apagar"
                            onClicked: { project.deleteFrame(page.selected); page.selected = Math.min(page.selected, page.count - 1) }
                        }
                    }
                }
            }
        }

        // ── filmstrip ─────────────────────────────────────────
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
                onCountChanged: positionViewAtEnd()
                currentIndex: page.playing ? page.playIndex : page.selected
                delegate: Rectangle {
                    width: 118; height: strip.height
                    radius: 6
                    color: "#0E1422"
                    border.width: 2
                    border.color: index === strip.currentIndex ? Theme.accent : "transparent"
                    Image {
                        anchors.fill: parent; anchors.margins: 3
                        source: modelData.url
                        sourceSize.width: 220
                        fillMode: Image.PreserveAspectCrop
                        asynchronous: true
                    }
                    Rectangle {
                        anchors.left: parent.left; anchors.bottom: parent.bottom; anchors.margins: 5
                        radius: 4; color: "#B3000000"; width: num.implicitWidth + 10; height: 18
                        Text { id: num; anchors.centerIn: parent; text: index + 1; color: "white"; font.pixelSize: 11 }
                    }
                    Rectangle {
                        visible: modelData.hold > 1
                        anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 5
                        radius: 4; color: Theme.warn; width: hl.implicitWidth + 10; height: 18
                        Text { id: hl; anchors.centerIn: parent; text: modelData.hold + "×"; color: "#1A1A1A"; font.pixelSize: 11; font.weight: Font.Bold }
                    }
                    MouseArea { anchors.fill: parent; onClicked: { page.stopPlayback(); page.selected = index } }
                }
                Text {
                    anchors.centerIn: parent
                    visible: strip.count === 0
                    text: "Os quadros capturados aparecem aqui — Espaço captura, Backspace apaga o último"
                    color: Theme.textDim; font.pixelSize: 14
                }
            }
        }
    }
}
