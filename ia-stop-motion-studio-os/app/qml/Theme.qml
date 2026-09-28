pragma Singleton
import QtQuick

QtObject {
    readonly property color bg: "#0B1220"
    readonly property color bgWarm: "#2A1A10"
    readonly property color panel: "#CC111A2B"
    readonly property color panelSolid: "#131D30"
    readonly property color panelBorder: "#33FFFFFF"
    readonly property color text: "#E8EEFC"
    readonly property color textDim: "#9AA8C4"
    readonly property color accent: "#2E8BFF"
    readonly property color accentSoft: "#332E8BFF"
    readonly property color cpu: "#2EA8FF"
    readonly property color ram: "#9B5CFF"
    readonly property color gpu: "#3BD67A"
    readonly property color warn: "#FFB547"
    readonly property color danger: "#FF5D5D"
    readonly property color felt: "#2F7DE1"
    readonly property color cream: "#F4E9D3"

    readonly property int radius: 14
    readonly property int topBarHeight: 44
    readonly property int sidebarWidth: 212

    function icon(name) {
        return "qrc:/StopMotionStudio/icons/" + name + ".svg"
    }
}
