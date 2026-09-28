import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import QtMultimedia
import StopMotionStudio

Item {
    id: page
    focus: true

    property int playhead: 0
    property bool playing: false
    property string selType: ""      // "video" | "title" | "audio"
    property int selIndex: -1
    property real ppf: 4              // pixels per frame (zoom)
    property var layers: timeline.layersAt(playhead)
    property string toast

    readonly property int fps: timeline.fps
    readonly property int duration: timeline.duration
    readonly property var selVideo: selType === "video" ? timeline.videoClips[selIndex] : undefined
    readonly property var selTitle: selType === "title" ? timeline.titles[selIndex] : undefined
    readonly property var selAudio: selType === "audio" ? timeline.audioClips[selIndex] : undefined

    Component.onCompleted: { fitZoom(); page.forceActiveFocus() }

    Connections {
        target: timeline
        function onChanged() {
            page.layers = timeline.layersAt(page.playhead)
            const n = page.selType === "video" ? timeline.videoClips.length
                    : page.selType === "title" ? timeline.titles.length
                    : page.selType === "audio" ? timeline.audioClips.length : 0
            if (page.selIndex >= n) { page.selType = ""; page.selIndex = -1 }
        }
        function onErrorOccurred(message) { page.notify(message) }
    }
    Connections {
        target: timelineRenderer
        function onFinished(ok, output) { page.notify(timelineRenderer.status) }
    }

    onPlayheadChanged: { layers = timeline.layersAt(playhead); syncAudio() }

    function notify(text) { toast = text; toastTimer.restart() }
    function fitZoom() {
        const w = tracksFlick.width - 20
        ppf = duration > 0 ? Math.max(0.3, Math.min(12, w / duration)) : 4
    }
    function select(type, index) { selType = type; selIndex = index }
    function togglePlay() {
        if (duration === 0) return
        if (!playing && playhead >= duration - 1) playhead = 0
        playing = !playing
        syncAudio()
    }
    function removeSelected() {
        if (selType === "video") timeline.removeVideo(selIndex)
        else if (selType === "title") timeline.removeTitle(selIndex)
        else if (selType === "audio") timeline.removeAudio(selIndex)
        selType = ""; selIndex = -1
    }
    function split() {
        if (!timeline.splitAt(playhead)) notify("Posicione o cursor dentro de um clipe de vídeo para dividir.")
    }
    function dbToLinear(db) { return Math.min(1, Math.pow(10, db / 20)) }

    // Keeps one MediaPlayer per audio clip in step with the playhead.
    function syncAudio() {
        for (let i = 0; i < audioPlayers.count; ++i) {
            const item = audioPlayers.itemAt(i)
            if (item) item.sync()
        }
    }

    Timer {
        interval: 1000 / page.fps
        repeat: true
        running: page.playing
        onTriggered: {
            if (page.playhead + 1 >= page.duration) { page.playing = false; page.syncAudio(); return }
            page.playhead += 1
        }
    }
    Timer { id: toastTimer; interval: 4000; onTriggered: page.toast = "" }

    Repeater {
        id: audioPlayers
        model: timeline.audioClips
        delegate: Item {
            required property var modelData
            function sync() {
                const local = (page.playhead - modelData.start + modelData.in) / page.fps * 1000
                const inside = page.playhead >= modelData.start && page.playhead < modelData.start + modelData.length
                if (page.playing && inside) {
                    if (player.playbackState !== MediaPlayer.PlayingState) { player.position = local; player.play() }
                    else if (Math.abs(player.position - local) > 250) player.position = local
                } else if (player.playbackState === MediaPlayer.PlayingState) {
                    player.pause()
                }
            }
            MediaPlayer {
                id: player
                source: modelData.source
                audioOutput: AudioOutput { volume: page.dbToLinear(modelData.volume) }
            }
        }
    }

    Shortcut { sequence: "Space"; onActivated: page.togglePlay() }
    Shortcut { sequences: [StandardKey.Undo]; onActivated: timeline.undo() }
    Shortcut { sequences: [StandardKey.Redo, "Ctrl+Shift+Z"]; onActivated: timeline.redo() }
    Shortcut { sequence: "S"; onActivated: page.split() }
    Shortcut { sequence: StandardKey.Delete; onActivated: page.removeSelected() }
    Shortcut { sequence: "Left"; onActivated: page.playhead = Math.max(0, page.playhead - 1) }
    Shortcut { sequence: "Right"; onActivated: page.playhead = Math.min(Math.max(0, page.duration - 1), page.playhead + 1) }
    Shortcut { sequence: "Home"; onActivated: page.playhead = 0 }
    Shortcut { sequence: "End"; onActivated: page.playhead = Math.max(0, page.duration - 1) }

    FileDialog {
        id: mediaDialog
        title: "Adicionar mídia"
        fileMode: FileDialog.OpenFiles
        nameFilters: ["Mídia (*.mp4 *.mov *.mkv *.webm *.avi *.png *.jpg *.jpeg *.webp *.wav *.mp3 *.ogg *.flac *.m4a *.opus)",
                      "Vídeos (*.mp4 *.mov *.mkv *.webm *.avi)", "Imagens (*.png *.jpg *.jpeg *.webp)",
                      "Áudio (*.wav *.mp3 *.ogg *.flac *.m4a *.opus)"]
        onAccepted: page.notify(timeline.addMedia(selectedFiles, page.playhead) + " arquivo(s) adicionado(s)")
    }

    Menu {
        id: sceneMenu
        Instantiator {
            model: timeline.availableScenes
            delegate: MenuItem {
                text: modelData.name + "  (" + modelData.frames + " quadros)"
                onTriggered: timeline.addScene(modelData.path)
            }
            onObjectAdded: (index, object) => sceneMenu.insertItem(index, object)
            onObjectRemoved: (index, object) => sceneMenu.removeItem(object)
        }
    }

    Popup {
        id: exportPopup
        anchors.centerIn: parent
        width: 520
        modal: true
        padding: 22
        property bool useGpu: exporter.vaapiAvailable
        background: Rectangle { radius: Theme.radius; color: Theme.panelSolid; border.color: Theme.panelBorder }
        contentItem: ColumnLayout {
            spacing: 14
            Text { text: "Exportar filme"; color: Theme.text; font.pixelSize: 22; font.weight: Font.DemiBold }
            Text {
                text: timeline.videoClips.length + " clipes · " + timeline.titles.length + " títulos · "
                      + timeline.audioClips.length + " áudios · " + timeline.timecode(page.duration)
                      + " · " + timeline.frameSize.width + "×" + timeline.frameSize.height + " · " + page.fps + " fps"
                color: Theme.textDim; font.pixelSize: 14
            }
            RowLayout {
                Switch {
                    checked: exportPopup.useGpu; enabled: exporter.vaapiAvailable
                    onToggled: exportPopup.useGpu = checked; focusPolicy: Qt.NoFocus
                }
                Text {
                    text: exporter.vaapiAvailable ? "Usar o encoder da GPU (VAAPI)" : "Encoder da GPU indisponível — usando CPU (x264)"
                    color: Theme.text; font.pixelSize: 14
                }
            }
            ProgressBar { Layout.fillWidth: true; value: timelineRenderer.progress; visible: timelineRenderer.busy || timelineRenderer.progress > 0 }
            Text { text: timelineRenderer.status; color: Theme.text; font.pixelSize: 13; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            RowLayout {
                spacing: 10
                IconButton {
                    iconName: "export"; text: timelineRenderer.busy ? "Renderizando…" : "Exportar MP4"
                    highlighted: true; enabled: !timelineRenderer.busy && timeline.videoClips.length > 0
                    onClicked: timelineRenderer.render(exportPopup.useGpu)
                }
                IconButton { iconName: "stop"; text: "Cancelar"; visible: timelineRenderer.busy; onClicked: timelineRenderer.cancel() }
                IconButton {
                    iconName: "folder"; text: "Abrir pasta"
                    visible: timelineRenderer.lastOutput.length > 0
                    onClicked: Qt.openUrlExternally("file://" + project.projectPath + "/export")
                }
                Item { Layout.fillWidth: true }
                IconButton {
                    iconName: "timeline"; tip: "Salva filme.mlt, que abre no Shotcut e no Kdenlive"
                    text: "Projeto MLT"
                    onClicked: {
                        const f = timelineRenderer.writeProject()
                        page.notify(f ? "Salvo: " + f : "Falha ao salvar o projeto MLT")
                    }
                }
            }
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 10

        // ── toolbar ─────────────────────────────────────────────
        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            Text {
                text: "Timeline"
                color: Theme.text; font.pixelSize: 20; font.weight: Font.DemiBold
            }
            Text {
                text: project.projectName ? "· " + project.projectName : ""
                color: Theme.textDim; font.pixelSize: 16; elide: Text.ElideRight
                Layout.maximumWidth: 220
            }
            Item { Layout.preferredWidth: 6 }
            IconButton { iconName: "clapper"; text: "Cena"; tip: "Adicionar uma cena capturada"; onClicked: sceneMenu.popup() }
            IconButton { iconName: "import"; text: "Mídia"; tip: "Vídeos, fotos, música, narração"; onClicked: mediaDialog.open() }
            IconButton { iconName: "plus"; text: "Título"; onClicked: { timeline.addTitle("Título", page.playhead); page.select("title", timeline.titles.length - 1) } }
            IconButton { iconName: "scenes"; text: "Dividir"; tip: "Divide o clipe no cursor (S)"; onClicked: page.split() }
            IconButton { iconName: "trash"; tip: "Apagar seleção (Delete)"; enabled: page.selIndex >= 0; onClicked: page.removeSelected() }
            Rectangle { width: 1; height: 26; color: "#33FFFFFF" }
            IconButton { text: "↶"; tip: "Desfazer (Ctrl+Z)"; enabled: timeline.canUndo; onClicked: timeline.undo() }
            IconButton { text: "↷"; tip: "Refazer (Ctrl+Shift+Z)"; enabled: timeline.canRedo; onClicked: timeline.redo() }
            Item { Layout.fillWidth: true }
            ComboBox {
                Layout.preferredWidth: 170
                focusPolicy: Qt.NoFocus
                model: [{ id: "youtube", t: "16:9 YouTube" }, { id: "vertical", t: "9:16 Reels/TikTok" },
                        { id: "quadrado", t: "1:1 Quadrado" }, { id: "4k", t: "4K 16:9" }]
                textRole: "t"
                currentIndex: model.findIndex(m => m.id === timeline.format)
                onActivated: (i) => timeline.format = model[i].id
            }
            ComboBox {
                Layout.preferredWidth: 100
                focusPolicy: Qt.NoFocus
                model: [12, 24, 25, 30]
                displayText: timeline.fps + " fps"
                currentIndex: model.indexOf(timeline.fps)
                onActivated: (i) => { timeline.fps = model[i]; page.fitZoom() }
            }
            IconButton { iconName: "export"; text: "Exportar filme"; highlighted: true; onClicked: exportPopup.open() }
        }

        // ── monitor + inspector ────────────────────────────────
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 12

            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 6

                Rectangle {
                    id: monitorBox
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    radius: 10
                    color: "#05070C"
                    clip: true

                    // Frame area with the timeline's aspect ratio.
                    Item {
                        id: frameArea
                        readonly property real aspect: timeline.frameSize.width / timeline.frameSize.height
                        width: Math.min(parent.width - 16, (parent.height - 16) * aspect)
                        height: width / aspect
                        anchors.centerIn: parent
                        Rectangle { anchors.fill: parent; color: "black" }

                        Repeater {
                            model: page.layers
                            delegate: Item {
                                anchors.fill: parent
                                opacity: modelData.opacity
                                Image {
                                    anchors.fill: parent
                                    visible: modelData.kind !== "video"
                                    source: modelData.kind !== "video" ? modelData.url : ""
                                    fillMode: Image.PreserveAspectFit
                                    sourceSize.width: frameArea.width
                                    asynchronous: false
                                    cache: true
                                }
                                // Media player only for video-file layers.
                                Loader {
                                    anchors.fill: parent
                                    active: modelData.kind === "video"
                                    sourceComponent: Item {
                                        VideoOutput { id: vout; anchors.fill: parent }
                                        MediaPlayer {
                                            id: vplayer
                                            source: modelData.url
                                            videoOutput: vout
                                            audioOutput: AudioOutput { volume: page.playing ? 1 : 0 }
                                            readonly property real target: modelData.seconds * 1000
                                            onTargetChanged: {
                                                if (!page.playing) position = target
                                                else if (Math.abs(position - target) > 300) position = target
                                            }
                                            Component.onCompleted: { position = target; if (page.playing) play() }
                                        }
                                        Connections {
                                            target: page
                                            function onPlayingChanged() { page.playing ? vplayer.play() : vplayer.pause() }
                                        }
                                    }
                                }
                            }
                        }

                        Column {
                            anchors.centerIn: parent
                            spacing: 8
                            visible: timeline.videoClips.length === 0
                            Image { source: Theme.icon("timeline"); width: 56; height: 56; sourceSize: Qt.size(112, 112); anchors.horizontalCenter: parent.horizontalCenter; opacity: 0.6 }
                            Text { text: "Monte seu filme"; color: Theme.text; font.pixelSize: 20; anchors.horizontalCenter: parent.horizontalCenter }
                            Text { text: "Adicione cenas capturadas, vídeos, fotos, títulos e música."; color: Theme.textDim; font.pixelSize: 14; anchors.horizontalCenter: parent.horizontalCenter }
                        }
                    }

                    Rectangle {
                        visible: page.toast.length > 0
                        anchors.horizontalCenter: parent.horizontalCenter
                        anchors.bottom: parent.bottom; anchors.bottomMargin: 14
                        radius: 8; color: "#E6131D30"; border.color: Theme.panelBorder
                        width: Math.min(toastText.implicitWidth + 28, parent.width - 40); height: 34
                        Text { id: toastText; anchors.centerIn: parent; width: parent.width - 28; elide: Text.ElideMiddle; horizontalAlignment: Text.AlignHCenter; text: page.toast; color: Theme.text; font.pixelSize: 13 }
                    }
                }

                // transport
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    IconButton { iconName: "undo"; tip: "Início (Home)"; onClicked: page.playhead = 0 }
                    IconButton { iconName: page.playing ? "stop" : "play"; highlighted: page.playing; tip: "Reproduzir / pausar (Espaço)"; onClicked: page.togglePlay() }
                    Text {
                        text: timeline.timecode(page.playhead) + "  /  " + timeline.timecode(page.duration)
                        color: Theme.text; font.pixelSize: 15; font.family: "monospace"
                    }
                    Item { Layout.fillWidth: true }
                    Text { text: "Zoom"; color: Theme.textDim; font.pixelSize: 13 }
                    Slider {
                        Layout.preferredWidth: 160
                        from: 0.3; to: 12
                        value: page.ppf
                        onMoved: page.ppf = value
                        focusPolicy: Qt.NoFocus
                    }
                    IconButton { iconName: "search"; tip: "Ajustar à largura"; onClicked: page.fitZoom() }
                }
            }

            // inspector
            Rectangle {
                Layout.preferredWidth: 300
                Layout.fillWidth: false
                Layout.fillHeight: true
                radius: 10
                color: Theme.panel
                border.color: "#1FFFFFFF"

                Flickable {
                    anchors.fill: parent
                    anchors.margins: 14
                    contentHeight: inspector.implicitHeight
                    clip: true

                    ColumnLayout {
                        id: inspector
                        width: parent.width
                        spacing: 10

                        // ── nothing selected
                        ColumnLayout {
                            visible: page.selIndex < 0
                            spacing: 8
                            Layout.fillWidth: true
                            Text { text: "Propriedades"; color: Theme.text; font.pixelSize: 17; font.weight: Font.DemiBold }
                            Text {
                                Layout.fillWidth: true
                                wrapMode: Text.WordWrap
                                color: Theme.textDim; font.pixelSize: 13
                                text: "Selecione um clipe na timeline.\n\nAtalhos:\nEspaço — reproduzir/pausar\nS — dividir no cursor\nDelete — apagar seleção\nCtrl+Z / Ctrl+Shift+Z — desfazer / refazer\n← → — quadro a quadro\n\nArraste clipes de vídeo para reordenar; títulos e áudios para mudar o início. Arraste a borda direita de um clipe para encurtar ou alongar."
                            }
                        }

                        // ── video clip
                        ColumnLayout {
                            visible: page.selVideo !== undefined
                            Layout.fillWidth: true
                            spacing: 10
                            Text {
                                text: page.selVideo ? page.selVideo.name : ""
                                color: Theme.text; font.pixelSize: 17; font.weight: Font.DemiBold
                                elide: Text.ElideRight; Layout.fillWidth: true
                            }
                            Text {
                                text: page.selVideo ? ({ scene: "Cena stop motion", video: "Vídeo", image: "Imagem" })[page.selVideo.type] : ""
                                color: Theme.textDim; font.pixelSize: 13
                            }
                            FrameSpin {
                                Layout.fillWidth: true
                                label: "Duração"; fps: page.fps
                                from: 1; to: page.selVideo && page.selVideo.sourceLength > 0 ? page.selVideo.sourceLength - page.selVideo.in : 3600 * page.fps
                                value: page.selVideo ? page.selVideo.length : 0
                                onEdited: (v) => timeline.setVideoProperty(page.selIndex, "length", v)
                            }
                            FrameSpin {
                                Layout.fillWidth: true
                                visible: page.selVideo !== undefined && page.selVideo.type !== "image"
                                label: "Começar do original em"; fps: page.fps
                                from: 0; to: page.selVideo ? Math.max(0, page.selVideo.out - 1) : 0
                                value: page.selVideo ? page.selVideo.in : 0
                                onEdited: (v) => timeline.setVideoProperty(page.selIndex, "in", v)
                            }
                            FrameSpin {
                                Layout.fillWidth: true
                                visible: page.selIndex > 0
                                label: "Dissolver a partir do clipe anterior"; fps: page.fps
                                from: 0; to: 10 * page.fps
                                value: page.selVideo ? page.selVideo.transition : 0
                                onEdited: (v) => timeline.setVideoProperty(page.selIndex, "transition", v)
                            }
                            ColumnLayout {
                                visible: page.selVideo !== undefined && page.selVideo.type === "video"
                                spacing: 2
                                Layout.fillWidth: true
                                Text { text: "Volume do vídeo: " + (page.selVideo ? page.selVideo.volume.toFixed(0) : 0) + " dB"; color: Theme.textDim; font.pixelSize: 12 }
                                Slider {
                                    Layout.fillWidth: true; from: -40; to: 6; stepSize: 1
                                    value: page.selVideo ? page.selVideo.volume : 0
                                    onMoved: timeline.setVideoProperty(page.selIndex, "volume", value)
                                    focusPolicy: Qt.NoFocus
                                }
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                IconButton { text: "◀"; tip: "Mover para a esquerda"; enabled: page.selIndex > 0; onClicked: { timeline.moveClip(page.selIndex, -1); page.selIndex -= 1 } }
                                IconButton { text: "▶"; tip: "Mover para a direita"; enabled: page.selIndex < timeline.videoClips.length - 1; onClicked: { timeline.moveClip(page.selIndex, 1); page.selIndex += 1 } }
                                Item { Layout.fillWidth: true }
                                IconButton { iconName: "trash"; text: "Apagar"; onClicked: page.removeSelected() }
                            }
                        }

                        // ── title
                        ColumnLayout {
                            visible: page.selTitle !== undefined
                            Layout.fillWidth: true
                            spacing: 10
                            Text { text: "Título"; color: Theme.text; font.pixelSize: 17; font.weight: Font.DemiBold }
                            TextArea {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 70
                                text: page.selTitle ? page.selTitle.text : ""
                                wrapMode: TextEdit.Wrap
                                color: Theme.text
                                background: Rectangle { radius: 6; color: "#1C2740"; border.color: Theme.panelBorder }
                                onEditingFinished: if (page.selTitle && text !== page.selTitle.text) timeline.setTitleProperty(page.selIndex, "text", text)
                            }
                            FrameSpin {
                                Layout.fillWidth: true
                                label: "Início"; fps: page.fps
                                value: page.selTitle ? page.selTitle.start : 0
                                onEdited: (v) => timeline.setTitleProperty(page.selIndex, "start", v)
                            }
                            FrameSpin {
                                Layout.fillWidth: true
                                label: "Duração"; fps: page.fps; from: 1
                                value: page.selTitle ? page.selTitle.length : 0
                                onEdited: (v) => timeline.setTitleProperty(page.selIndex, "length", v)
                            }
                            Text { text: "Posição"; color: Theme.textDim; font.pixelSize: 12 }
                            RowLayout {
                                Repeater {
                                    model: [{ id: "top", t: "Topo" }, { id: "center", t: "Centro" }, { id: "bottom", t: "Rodapé" }]
                                    IconButton {
                                        text: modelData.t
                                        highlighted: page.selTitle !== undefined && page.selTitle.position === modelData.id
                                        onClicked: timeline.setTitleProperty(page.selIndex, "position", modelData.id)
                                    }
                                }
                            }
                            Text { text: "Tamanho: " + (page.selTitle ? page.selTitle.size : 8) + "%"; color: Theme.textDim; font.pixelSize: 12 }
                            Slider {
                                Layout.fillWidth: true; from: 3; to: 20; stepSize: 1
                                value: page.selTitle ? page.selTitle.size : 8
                                onMoved: timeline.setTitleProperty(page.selIndex, "size", value)
                                focusPolicy: Qt.NoFocus
                            }
                            RowLayout {
                                spacing: 6
                                Repeater {
                                    model: ["#FFFFFF", "#FFE066", "#F4E9D3", "#6FB3FF", "#FF7A7A", "#111111"]
                                    Rectangle {
                                        width: 28; height: 28; radius: 14; color: modelData
                                        border.width: page.selTitle !== undefined && page.selTitle.color.toUpperCase() === modelData ? 3 : 1
                                        border.color: page.selTitle !== undefined && page.selTitle.color.toUpperCase() === modelData ? Theme.accent : "#55FFFFFF"
                                        MouseArea { anchors.fill: parent; onClicked: timeline.setTitleProperty(page.selIndex, "color", modelData) }
                                    }
                                }
                            }
                            RowLayout {
                                Switch {
                                    checked: page.selTitle ? page.selTitle.box : true
                                    onToggled: timeline.setTitleProperty(page.selIndex, "box", checked)
                                    focusPolicy: Qt.NoFocus
                                }
                                Text { text: "Faixa escura atrás do texto"; color: Theme.text; font.pixelSize: 13 }
                            }
                            IconButton { iconName: "trash"; text: "Apagar título"; onClicked: page.removeSelected() }
                        }

                        // ── audio
                        ColumnLayout {
                            visible: page.selAudio !== undefined
                            Layout.fillWidth: true
                            spacing: 10
                            Text {
                                text: page.selAudio ? page.selAudio.name : ""
                                color: Theme.text; font.pixelSize: 17; font.weight: Font.DemiBold
                                elide: Text.ElideRight; Layout.fillWidth: true
                            }
                            Text { text: "Áudio"; color: Theme.textDim; font.pixelSize: 13 }
                            FrameSpin {
                                Layout.fillWidth: true
                                label: "Início"; fps: page.fps
                                value: page.selAudio ? page.selAudio.start : 0
                                onEdited: (v) => timeline.setAudioProperty(page.selIndex, "start", v)
                            }
                            FrameSpin {
                                Layout.fillWidth: true
                                label: "Duração"; fps: page.fps; from: 1
                                to: page.selAudio && page.selAudio.sourceLength > 0 ? page.selAudio.sourceLength - page.selAudio.in : 3600 * page.fps
                                value: page.selAudio ? page.selAudio.length : 0
                                onEdited: (v) => timeline.setAudioProperty(page.selIndex, "length", v)
                            }
                            Text { text: "Volume: " + (page.selAudio ? page.selAudio.volume.toFixed(0) : 0) + " dB"; color: Theme.textDim; font.pixelSize: 12 }
                            Slider {
                                Layout.fillWidth: true; from: -40; to: 6; stepSize: 1
                                value: page.selAudio ? page.selAudio.volume : 0
                                onMoved: timeline.setAudioProperty(page.selIndex, "volume", value)
                                focusPolicy: Qt.NoFocus
                            }
                            IconButton { iconName: "trash"; text: "Apagar áudio"; onClicked: page.removeSelected() }
                        }
                    }
                }
            }
        }

        // ── tracks ─────────────────────────────────────────────
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 208
            radius: 10
            color: Theme.panel
            border.color: "#1FFFFFFF"

            readonly property int rulerH: 24
            readonly property int videoH: 72
            readonly property int titleH: 40
            readonly property int audioH: 48

            Column {
                id: labels
                x: 8; y: 8 + parent.rulerH
                width: 86
                spacing: 4
                Repeater {
                    model: [{ t: "Vídeo", i: "clapper", h: 72 }, { t: "Títulos", i: "plus", h: 40 }, { t: "Áudio", i: "live", h: 48 }]
                    Rectangle {
                        width: labels.width; height: modelData.h; radius: 6; color: "#14FFFFFF"
                        Row {
                            anchors.centerIn: parent; spacing: 6
                            Image { source: Theme.icon(modelData.i); width: 16; height: 16; sourceSize: Qt.size(32, 32); anchors.verticalCenter: parent.verticalCenter }
                            Text { text: modelData.t; color: Theme.text; font.pixelSize: 13 }
                        }
                    }
                }
            }

            Flickable {
                id: tracksFlick
                anchors { left: labels.right; leftMargin: 8; right: parent.right; rightMargin: 8; top: parent.top; topMargin: 8; bottom: parent.bottom; bottomMargin: 8 }
                clip: true
                contentWidth: Math.max(width, (page.duration + 5 * page.fps) * page.ppf)
                contentHeight: height
                boundsBehavior: Flickable.StopAtBounds
                interactive: false
                ScrollBar.horizontal: ScrollBar { policy: ScrollBar.AsNeeded }
                onWidthChanged: if (page.duration > 0 && page.ppf === 4) page.fitZoom()

                WheelHandler {
                    orientation: Qt.Vertical
                    onWheel: (e) => tracksFlick.contentX = Math.max(0, Math.min(tracksFlick.contentWidth - tracksFlick.width, tracksFlick.contentX - e.angleDelta.y))
                }

                Item {
                    id: lanes
                    width: tracksFlick.contentWidth
                    height: tracksFlick.height
                    readonly property int rulerH: 24
                    readonly property int videoY: rulerH
                    readonly property int titleY: rulerH + 72 + 4
                    readonly property int audioY: rulerH + 72 + 4 + 40 + 4

                    // ruler — click or drag to move the playhead
                    Item {
                        width: parent.width; height: parent.height
                        Repeater {
                            model: Math.ceil(lanes.width / (page.fps * page.ppf)) + 1
                            Item {
                                readonly property int step: page.ppf * page.fps < 40 ? 5 : 1
                                visible: index % step === 0
                                x: index * page.fps * page.ppf
                                Rectangle { width: 1; height: 8; y: 14; color: "#66FFFFFF" }
                                Text { x: 3; y: 0; text: Math.floor(index / 60) + ":" + String(index % 60).padStart(2, "0"); color: Theme.textDim; font.pixelSize: 11 }
                            }
                        }
                        MouseArea {
                            width: parent.width; height: lanes.rulerH
                            onPressed: (m) => { page.playing = false; page.playhead = Math.max(0, Math.round(m.x / page.ppf)) }
                            onPositionChanged: (m) => page.playhead = Math.max(0, Math.round(m.x / page.ppf))
                        }
                    }

                    // lane backgrounds (click empty space = move playhead, clear selection)
                    Repeater {
                        model: [{ y: lanes.videoY, h: 72 }, { y: lanes.titleY, h: 40 }, { y: lanes.audioY, h: 48 }]
                        Rectangle {
                            y: modelData.y; width: lanes.width; height: modelData.h
                            radius: 6; color: "#0DFFFFFF"
                            MouseArea {
                                anchors.fill: parent
                                onClicked: (m) => { page.select("", -1); page.playhead = Math.round(m.x / page.ppf) }
                            }
                        }
                    }

                    // video clips
                    Repeater {
                        model: timeline.videoClips
                        delegate: Rectangle {
                            id: vclip
                            readonly property bool selected: page.selType === "video" && page.selIndex === index
                            property real dragLength: -1
                            property real dragOffset: 0
                            x: modelData.start * page.ppf + dragOffset
                            y: lanes.videoY + (index % 2 ? 4 : 0) - (dragOffset !== 0 ? 6 : 0)
                            opacity: dragOffset !== 0 ? 0.85 : 1
                            width: Math.max(6, (dragLength >= 0 ? dragLength : modelData.length) * page.ppf)
                            height: 68
                            radius: 6
                            clip: true
                            color: modelData.type === "scene" ? "#3A6FD8" : modelData.type === "video" ? "#6A4FD0" : "#2F8F7A"
                            border.width: selected ? 2 : 1
                            border.color: selected ? "white" : "#55FFFFFF"
                            z: dragOffset !== 0 ? 5 : selected ? 2 : 1
                            Image {
                                x: 3; y: 3; height: parent.height - 6; width: Math.min(parent.width - 6, height * 1.4)
                                source: modelData.thumbnail
                                fillMode: Image.PreserveAspectCrop
                                sourceSize.width: 160
                                asynchronous: true
                            }
                            Text {
                                x: Math.min(parent.width - 6, parent.height * 1.4 + 8); y: 6
                                width: parent.width - x - 6
                                text: modelData.name; color: "white"; font.pixelSize: 12; font.weight: Font.DemiBold
                                elide: Text.ElideRight
                            }
                            Text {
                                x: Math.min(parent.width - 6, parent.height * 1.4 + 8); y: 24
                                text: timeline.timecode(modelData.length); color: "#DDEBFF"; font.pixelSize: 11
                            }
                            // dissolve marker
                            Canvas {
                                visible: modelData.transition > 0
                                width: modelData.transition * page.ppf; height: parent.height
                                onWidthChanged: requestPaint()
                                onPaint: {
                                    const c = getContext("2d"); c.reset()
                                    c.fillStyle = "rgba(255,255,255,0.28)"
                                    c.beginPath(); c.moveTo(0, height); c.lineTo(width, 0); c.lineTo(0, 0); c.closePath(); c.fill()
                                }
                            }
                            // Click selects; dragging sideways reorders the clip.
                            MouseArea {
                                anchors.fill: parent
                                property real pressX
                                property bool dragging: false
                                cursorShape: dragging ? Qt.ClosedHandCursor : Qt.PointingHandCursor
                                onPressed: (m) => { pressX = mapToItem(lanes, m.x, 0).x; dragging = false }
                                onPositionChanged: (m) => {
                                    const dx = mapToItem(lanes, m.x, 0).x - pressX
                                    if (!dragging && Math.abs(dx) > 8) { dragging = true; page.select("video", index) }
                                    if (dragging) vclip.dragOffset = dx
                                }
                                onReleased: (m) => {
                                    if (!dragging) {
                                        page.select("video", index)
                                        page.playhead = modelData.start + Math.round(m.x / page.ppf)
                                        return
                                    }
                                    // Drop position: the clip's centre among the others' centres.
                                    const centre = (modelData.start + modelData.length / 2) * page.ppf + vclip.dragOffset
                                    let target = 0
                                    const clips = timeline.videoClips
                                    for (let k = 0; k < clips.length; ++k) {
                                        if (k === index) continue
                                        if ((clips[k].start + clips[k].length / 2) * page.ppf < centre) target++
                                    }
                                    vclip.dragOffset = 0
                                    dragging = false
                                    if (target !== index) { timeline.moveClipTo(index, target); page.select("video", target) }
                                }
                            }
                            // trim handle
                            Rectangle {
                                anchors.right: parent.right; width: 8; height: parent.height
                                color: trim.containsMouse || trim.pressed ? "#AAFFFFFF" : "transparent"
                                MouseArea {
                                    id: trim
                                    anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.SizeHorCursor
                                    property real startX
                                    onPressed: (m) => { startX = mapToItem(lanes, m.x, 0).x; vclip.dragLength = modelData.length; page.select("video", index) }
                                    onPositionChanged: (m) => {
                                        const dx = mapToItem(lanes, m.x, 0).x - startX
                                        const max = modelData.sourceLength > 0 ? modelData.sourceLength - modelData.in : 1e9
                                        vclip.dragLength = Math.max(1, Math.min(max, modelData.length + Math.round(dx / page.ppf)))
                                    }
                                    onReleased: { const v = vclip.dragLength; vclip.dragLength = -1; timeline.setVideoProperty(index, "length", v) }
                                }
                            }
                        }
                    }

                    // titles
                    Repeater {
                        model: timeline.titles
                        delegate: Rectangle {
                            id: tclip
                            readonly property bool selected: page.selType === "title" && page.selIndex === index
                            property real dragLength: -1
                            x: modelData.start * page.ppf
                            y: lanes.titleY + 2
                            width: Math.max(6, (dragLength >= 0 ? dragLength : modelData.length) * page.ppf)
                            height: 36; radius: 6
                            color: "#C98A1E"
                            border.width: selected ? 2 : 1
                            border.color: selected ? "white" : "#55FFFFFF"
                            z: selected ? 2 : 1
                            Text { anchors.fill: parent; anchors.margins: 6; text: "T  " + modelData.text.replace(/\n/g, " "); color: "white"; font.pixelSize: 12; elide: Text.ElideRight; verticalAlignment: Text.AlignVCenter }
                            MouseArea {
                                anchors.fill: parent
                                drag.target: tclip; drag.axis: Drag.XAxis; drag.minimumX: 0
                                onPressed: page.select("title", index)
                                onReleased: timeline.setTitleProperty(index, "start", Math.round(tclip.x / page.ppf))
                            }
                            Rectangle {
                                anchors.right: parent.right; width: 8; height: parent.height
                                color: ttrim.containsMouse || ttrim.pressed ? "#AAFFFFFF" : "transparent"
                                MouseArea {
                                    id: ttrim
                                    anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.SizeHorCursor
                                    property real startX
                                    onPressed: (m) => { startX = mapToItem(lanes, m.x, 0).x; tclip.dragLength = modelData.length }
                                    onPositionChanged: (m) => tclip.dragLength = Math.max(1, modelData.length + Math.round((mapToItem(lanes, m.x, 0).x - startX) / page.ppf))
                                    onReleased: { const v = tclip.dragLength; tclip.dragLength = -1; timeline.setTitleProperty(index, "length", v) }
                                }
                            }
                        }
                    }

                    // audio
                    Repeater {
                        model: timeline.audioClips
                        delegate: Rectangle {
                            id: aclip
                            readonly property bool selected: page.selType === "audio" && page.selIndex === index
                            property real dragLength: -1
                            x: modelData.start * page.ppf
                            y: lanes.audioY + 2
                            width: Math.max(6, (dragLength >= 0 ? dragLength : modelData.length) * page.ppf)
                            height: 44; radius: 6
                            color: "#2E9A5A"
                            border.width: selected ? 2 : 1
                            border.color: selected ? "white" : "#55FFFFFF"
                            z: selected ? 2 : 1
                            clip: true
                            // decorative waveform
                            Row {
                                anchors.verticalCenter: parent.verticalCenter
                                spacing: 2; x: 4; opacity: 0.45
                                Repeater {
                                    model: Math.max(0, Math.floor((aclip.width - 8) / 4))
                                    Rectangle { width: 2; height: 6 + Math.abs(Math.sin(index * 0.7) * Math.cos(index * 0.23)) * 28; color: "white"; anchors.verticalCenter: parent.verticalCenter }
                                }
                            }
                            Rectangle {
                                x: 4; y: 3; radius: 4; color: "#B3143D25"
                                width: Math.min(parent.width - 8, audioName.implicitWidth + 10); height: 18
                                Text { id: audioName; x: 5; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 10; text: "♪ " + modelData.name; color: "white"; font.pixelSize: 12; font.weight: Font.DemiBold; elide: Text.ElideRight }
                            }
                            MouseArea {
                                anchors.fill: parent
                                drag.target: aclip; drag.axis: Drag.XAxis; drag.minimumX: 0
                                onPressed: page.select("audio", index)
                                onReleased: timeline.setAudioProperty(index, "start", Math.round(aclip.x / page.ppf))
                            }
                            Rectangle {
                                anchors.right: parent.right; width: 8; height: parent.height
                                color: atrim.containsMouse || atrim.pressed ? "#AAFFFFFF" : "transparent"
                                MouseArea {
                                    id: atrim
                                    anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.SizeHorCursor
                                    property real startX
                                    onPressed: (m) => { startX = mapToItem(lanes, m.x, 0).x; aclip.dragLength = modelData.length }
                                    onPositionChanged: (m) => {
                                        const max = modelData.sourceLength > 0 ? modelData.sourceLength - modelData.in : 1e9
                                        aclip.dragLength = Math.max(1, Math.min(max, modelData.length + Math.round((mapToItem(lanes, m.x, 0).x - startX) / page.ppf)))
                                    }
                                    onReleased: { const v = aclip.dragLength; aclip.dragLength = -1; timeline.setAudioProperty(index, "length", v) }
                                }
                            }
                        }
                    }

                    // playhead
                    Item {
                        x: page.playhead * page.ppf
                        height: parent.height
                        z: 10
                        Rectangle { x: -1; width: 2; height: parent.height; color: "#FF4D4D" }
                        Rectangle {
                            x: -7; y: 0; width: 14; height: 14; radius: 3; color: "#FF4D4D"
                            MouseArea {
                                anchors.fill: parent; anchors.margins: -6
                                cursorShape: Qt.SizeHorCursor
                                onPositionChanged: (m) => page.playhead = Math.max(0, Math.round(mapToItem(lanes, m.x, 0).x / page.ppf))
                            }
                        }
                    }
                }
            }
        }
    }
}
