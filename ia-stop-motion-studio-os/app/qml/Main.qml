import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import StopMotionStudio

ApplicationWindow {
    id: window
    width: 1672
    height: 941
    minimumWidth: 1280
    minimumHeight: 760
    visible: true
    title: "IA Stop-Motion Studio OS"
    color: Theme.bg

    // Dark palette for the stock Basic controls (ComboBox, Switch, dialogs…).
    palette {
        window: Theme.panelSolid
        windowText: Theme.text
        base: "#1C2740"
        alternateBase: "#22304A"
        text: Theme.text
        button: "#22304A"
        buttonText: Theme.text
        highlight: Theme.accent
        highlightedText: "white"
        light: "#2C3B58"
        midlight: "#26344F"
        mid: "#3A4A68"
        dark: Theme.accent      // checked Switch/CheckBox fill in the Basic style
        placeholderText: Theme.textDim
    }

    property string currentPage: "inicio"
    property bool autoPlay: false

    function navigate(page) {
        // The dock's "Player" opens the capture screen already playing.
        autoPlay = page === "player"
        currentPage = page === "player" ? "captura" : page
    }

    readonly property var pageInfo: ({
        editor: { title: "Editor de Cenas", icon: "scenes", step: 5, text: "Composição de cenários, chroma key dos bonecos de pano, remoção de suportes e fios com inpainting." },
        biblioteca: { title: "Biblioteca", icon: "library", step: 4, text: "Fotos, sons, trilhas, títulos e recursos reutilizáveis entre projetos." },
        projetos: { title: "Projetos", icon: "folder", step: 2, text: "Lista de projetos em " + project.baseDir + "/Projetos." },
        personagens: { title: "Personagens", icon: "user", step: 5, text: "Ficha de cada boneco: fotos de referência, bocas para sincronia labial, olhos e expressões." },
        cenarios: { title: "Cenários", icon: "image", step: 5, text: "Cenários fotografados e gerados por IA com estilo feltro/pano." },
        configuracoes: { title: "Configurações", icon: "settings", step: 6, text: "Câmera, pasta de projetos, perfis de desempenho do kernel (Captura, Edição, IA, Render)." },
        terminal: { title: "Terminal", icon: "terminal", step: 6, text: "Acesso ao terminal do sistema." },
        lixeira: { title: "Lixeira", icon: "trash", step: 2, text: "Quadros apagados ficam em <projeto>/lixeira e podem ser recuperados." },
        ajuda: { title: "Ajuda", icon: "help", step: 1, text: "Captura: Espaço captura · Backspace apaga o último · O onion skin · G grade · L ao vivo/último · P reproduzir.  Timeline: Espaço reproduz · S divide · Delete apaga · ← → quadro a quadro." }
    })

    background: Rectangle {
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#101A2E" }
            GradientStop { position: 0.55; color: "#141522" }
            GradientStop { position: 1.0; color: "#231811" }
        }
        // warm studio lamp glow
        Rectangle {
            x: parent.width * 0.52; y: -parent.height * 0.15
            width: parent.width * 0.5; height: width; radius: width / 2
            opacity: 0.16
            gradient: Gradient {
                GradientStop { position: 0.0; color: "#FFB45E" }
                GradientStop { position: 1.0; color: "transparent" }
            }
        }
    }

    header: TopBar {}

    Sidebar {
        id: sidebar
        x: 10; y: 34
        height: parent.height - 34 - (window.currentPage === "inicio" ? 150 : 140)
        currentPage: window.currentPage
        onNavigate: (page) => window.navigate(page)
    }

    Loader {
        id: pageLoader
        anchors {
            left: sidebar.right; leftMargin: 20
            right: parent.right; rightMargin: 16
            top: parent.top; topMargin: 34
            bottom: dock.top; bottomMargin: 14
        }
        sourceComponent: {
            switch (window.currentPage) {
            case "inicio": return homePage
            case "captura": return capturePage
            case "renderizacao": return renderPage
            case "timeline": return timelinePage
            case "ia": return aiPage
            default: return placeholderPage
            }
        }
    }

    Component { id: homePage; HomePage { onNavigate: (page) => window.navigate(page) } }
    Component { id: capturePage; CapturePage { autoPlay: window.autoPlay } }
    Component { id: renderPage; RenderPage {} }
    Component { id: timelinePage; TimelinePage {} }
    Component { id: aiPage; AiPage {} }
    Component {
        id: placeholderPage
        PlaceholderPage {
            readonly property var info: window.pageInfo[window.currentPage] || { title: window.currentPage, icon: "help", step: 0, text: "" }
            title: info.title; iconName: info.icon; step: info.step; description: info.text
        }
    }

    Dock {
        id: dock
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.horizontalCenterOffset: Theme.sidebarWidth / 2
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 12
        currentPage: window.currentPage
        onNavigate: (page) => window.navigate(page)
    }

    Column {
        anchors.left: parent.left; anchors.leftMargin: 22
        anchors.bottom: parent.bottom; anchors.bottomMargin: 26
        visible: window.width - dock.width > 2 * 260
        Text { text: "IA Stop-Motion Studio OS v" + appVersion; color: Theme.textDim; font.pixelSize: 13 }
        Text { text: "Built on Ubuntu 24.04 LTS"; color: Theme.textDim; font.pixelSize: 13 }
    }
}
