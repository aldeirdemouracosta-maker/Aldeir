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
    property bool showDopeSheet: project.audioName.length > 0
    // Video frame shown during playback (photos advance by their holds).
    property int playFrame: 0
    readonly property int nextFrame: project.totalFrames
    readonly property string nextMouth: audioTrack.mouths.length > nextFrame ? audioTrack.mouths[nextFrame] : ""

    // Webcams (QtMultimedia) and DSLR/mirrorless cameras (gPhoto2).
    readonly property var sources: {
        const list = mediaDevices.videoInputs.map((d, i) => ({ kind: "webcam", index: i, label: d.description }))
        for (const c of dslr.cameras) list.push({ kind: "dslr", port: c.port, label: "📷 " + c.model + " (DSLR)" })
        return list
    }
    readonly property var source: cameraBox.currentIndex >= 0 ? sources[cameraBox.currentIndex] : undefined
    readonly property bool isDslr: source !== undefined && source.kind === "dslr"
    readonly property bool hasCamera: sources.length > 0
    onIsDslrChanged: isDslr ? dslr.startLiveView(source.port) : dslr.stopLiveView()
    Component.onDestruction: dslr.stopLiveView()
    readonly property int count: project.frameCount

    Component.onCompleted: {
        project.attachImageCapture(imageCapture)
        dslr.detect()
        if (autoPlay && count > 0)
            startPlayback()
        page.forceActiveFocus()
    }

    Connections {
        target: project
        function onFrameSaved(index) { page.selected = index; flash.restart() }
        function onErrorOccurred(message) { page.notify(message) }
    }
    Connections {
        target: dslr
        function onCaptureFailed(message) { page.notify(message) }
        function onCamerasChanged() { if (dslr.cameras.length && !page.hasWebcamSelected()) cameraBox.currentIndex = Math.max(0, cameraBox.currentIndex) }
    }
    function hasWebcamSelected() { return source !== undefined && source.kind === "webcam" }

    function notify(text) { toast = text; toastTimer.restart() }

    function capture() {
        if (playing) stopPlayback()
        if (!hasCamera) { notify("Nenhuma câmera: conecte uma webcam/DSLR ou importe fotos."); return }
        if (isDslr) {
            if (!dslr.capture(source.port)) notify("A DSLR ainda está ocupada com a foto anterior.")
            return
        }
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
        playFrame = 0
        playing = true
        syncAudio(true)
    }
    function stopPlayback() { playing = false; audioPlayer.pause() }

    // Soundtrack position (ms) for a video frame, or -1 before it starts.
    function audioMs(frame) { return (frame - project.audioOffset) * 1000 / project.fps }

    function syncAudio(restart) {
        if (!project.audioFile) return
        const ms = audioMs(playFrame)
        if (ms < 0 || ms >= audioPlayer.duration) { audioPlayer.pause(); return }
        if (restart || audioPlayer.playbackState !== MediaPlayer.PlayingState) { audioPlayer.position = ms; audioPlayer.play() }
        else if (Math.abs(audioPlayer.position - ms) > 120) audioPlayer.position = ms
    }

    // Plays the second of audio leading up to (and including) the next frame.
    function listen() {
        if (!project.audioFile) { notify("Importe uma trilha de áudio no dope sheet."); return }
        if (playing) stopPlayback()
        const end = audioMs(nextFrame + 1)
        const start = Math.max(0, end - 1000)
        if (end <= 0) { notify("O áudio começa depois deste quadro."); return }
        audioPlayer.position = start
        audioPlayer.play()
        listenStop.interval = end - start
        listenStop.restart()
    }

    MediaDevices { id: mediaDevices }

    CaptureSession {
        camera: Camera {
            id: camera
            cameraDevice: page.hasWebcamSelected() ? mediaDevices.videoInputs[page.source.index] : mediaDevices.defaultVideoInput
            active: page.hasWebcamSelected()
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
            page.playFrame += 1
            if (--page.playHoldLeft > 0) { page.syncAudio(false); return }
            page.playIndex = (page.playIndex + 1) % page.count
            page.playHoldLeft = project.holdAt(page.playIndex)
            if (page.playIndex === 0) { page.playFrame = 0; page.syncAudio(true) }
            else page.syncAudio(false)
        }
    }
    Timer { id: toastTimer; interval: 3500; onTriggered: page.toast = "" }
    Timer { id: listenStop; onTriggered: audioPlayer.pause() }

    MediaPlayer {
        id: audioPlayer
        source: project.audioFile ? "file://" + project.audioFile : ""
        audioOutput: AudioOutput {}
    }

    Shortcut { sequence: "Space"; onActivated: page.capture() }
    Shortcut { sequence: "Backspace"; onActivated: project.deleteLastFrame() }
    Shortcut { sequence: "O"; onActivated: page.onionLayers = (page.onionLayers + 1) % 4 }
    Shortcut { sequence: "G"; onActivated: page.showGrid = !page.showGrid }
    Shortcut { sequence: "L"; onActivated: page.showLastFrame = !page.showLastFrame }
    Shortcut { sequence: "P"; onActivated: page.playing ? page.stopPlayback() : page.startPlayback() }
    Shortcut { sequence: "A"; onActivated: page.listen() }
    Shortcut { sequence: "D"; onActivated: page.showDopeSheet = !page.showDopeSheet }

    FileDialog {
        id: importDialog
        title: "Importar fotos"
        fileMode: FileDialog.OpenFiles
        nameFilters: ["Imagens (*.png *.jpg *.jpeg *.webp *.bmp)"]
        onAccepted: page.notify(project.importImages(selectedFiles) + " foto(s) importada(s)")
    }

    FileDialog {
        id: audioDialog
        title: "Trilha de áudio (falas, música)"
        nameFilters: ["Áudio (*.wav *.mp3 *.ogg *.flac *.m4a *.opus)"]
        onAccepted: if (project.setAudio(selectedFile)) page.showDopeSheet = true
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
                model: page.sources.map(s => s.label)
                displayText: page.hasCamera ? currentText : "Nenhuma câmera"
                enabled: page.hasCamera
                focusPolicy: Qt.NoFocus
            }
            IconButton {
                iconName: "search"; tip: "Procurar câmeras DSLR/mirrorless (gPhoto2)"
                enabled: dslr.available && !dslr.busy
                onClicked: dslr.detect()
            }
            IconButton {
                visible: !page.isDslr
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
            IconButton { iconName: "timeline"; highlighted: page.showDopeSheet; tip: "Dope sheet com a trilha de áudio (D)"; onClicked: page.showDopeSheet = !page.showDopeSheet }
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
                    visible: page.hasWebcamSelected() && !page.playing
                }
                // DSLR live view (movie stream through gPhoto2).
                Image {
                    anchors.fill: parent
                    fillMode: Image.PreserveAspectFit
                    visible: page.isDslr && !page.playing
                    source: page.isDslr ? "image://dslr/" + dslr.frameCounter : ""
                    cache: false
                    asynchronous: false
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
                                 : page.showLastFrame ? "ÚLTIMO QUADRO"
                                 : page.isDslr ? (dslr.busy ? "FOTOGRAFANDO…" : dslr.liveView ? "● DSLR AO VIVO" : "DSLR")
                                 : page.hasCamera ? "● AO VIVO" : "SEM CÂMERA"
                        }
                    }
                    Rectangle {
                        radius: 6; color: "#99000000"; width: fc.implicitWidth + 18; height: 26
                        Text { id: fc; anchors.centerIn: parent; color: "white"; font.pixelSize: 13; text: "Quadro " + (page.nextFrame + 1) + "  ·  " + project.durationText }
                    }
                }

                // Lip sync: mouth to put on the puppet for the next photo.
                Rectangle {
                    visible: page.nextMouth !== "" && !page.playing
                    anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 12
                    radius: 10; color: "#CC111A2B"; border.color: Theme.panelBorder
                    width: mouthRow.implicitWidth + 24; height: 64
                    Row {
                        id: mouthRow
                        anchors.centerIn: parent
                        spacing: 12
                        Rectangle {
                            width: 44; height: 44; radius: 8
                            color: dope.shapeColor(page.nextMouth)
                            Text { anchors.centerIn: parent; text: page.nextMouth; color: "#111"; font.pixelSize: 26; font.weight: Font.Black }
                        }
                        Column {
                            anchors.verticalCenter: parent.verticalCenter
                            Text { text: "Boca do próximo quadro"; color: Theme.textDim; font.pixelSize: 12 }
                            Text { text: audioTrack.mouthDescription(page.nextMouth); color: Theme.text; font.pixelSize: 15; font.weight: Font.DemiBold }
                        }
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

        DopeSheet {
            id: dope
            Layout.fillWidth: true
            Layout.preferredHeight: 146
            visible: page.showDopeSheet
            selected: page.selected
            playing: page.playing
            cursorFrame: page.playing ? page.playFrame : page.nextFrame
            onSelectPhoto: (index) => { page.stopPlayback(); page.selected = index }
            onImportAudio: audioDialog.open()
            onListen: page.listen()
        }

        // ── filmstrip ─────────────────────────────────────────
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: page.showDopeSheet ? 84 : 104
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
