import QtQuick
import QtQuick.Layouts
import StopMotionStudio

Rectangle {
    id: side
    property string currentPage
    signal navigate(string page)

    width: Theme.sidebarWidth
    radius: Theme.radius
    color: Theme.panel
    border.color: "#1FFFFFFF"

    readonly property var items: [
        { page: "inicio", label: "Início", icon: "home" },
        { page: "captura", label: "Captura", icon: "camera" },
        { page: "editor", label: "Editor de Cenas", icon: "scenes" },
        { page: "biblioteca", label: "Biblioteca", icon: "library" },
        { page: "projetos", label: "Projetos", icon: "folder" },
        { page: "ia", label: "IA Local", icon: "chip" },
        { page: "renderizacao", label: "Renderização", icon: "render" },
        { page: "personagens", label: "Personagens", icon: "user" },
        { page: "cenarios", label: "Cenários", icon: "image" },
        { page: "configuracoes", label: "Configurações", icon: "settings" },
        { page: "terminal", label: "Terminal", icon: "terminal" }
    ]

    component NavItem: Rectangle {
        id: nav
        property string page
        property string label
        property string iconName
        readonly property bool active: side.currentPage === page
        Layout.fillWidth: true
        Layout.preferredHeight: 46
        radius: 8
        color: active ? "#2E6FD0" : mouse.containsMouse ? "#18FFFFFF" : "transparent"
        Rectangle { visible: nav.active; width: 3; height: parent.height; anchors.right: parent.right; color: "#7FB6FF"; radius: 2 }
        Row {
            anchors.verticalCenter: parent.verticalCenter
            x: 16; spacing: 16
            Image { source: Theme.icon(nav.iconName); width: 24; height: 24; sourceSize: Qt.size(48, 48) }
            Text { text: nav.label; color: Theme.text; font.pixelSize: 15; anchors.verticalCenter: parent.verticalCenter }
        }
        MouseArea { id: mouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: side.navigate(nav.page) }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 8
        anchors.topMargin: 18
        spacing: 7
        Repeater {
            model: side.items
            NavItem { page: modelData.page; label: modelData.label; iconName: modelData.icon }
        }
        Item { Layout.fillHeight: true }
        NavItem { page: "ajuda"; label: "Ajuda"; iconName: "help" }
    }
}
