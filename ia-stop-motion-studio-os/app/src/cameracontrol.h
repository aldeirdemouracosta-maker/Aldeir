#pragma once

#include <QCameraDevice>
#include <QObject>

// Locks/unlocks webcam auto-exposure, auto white balance and autofocus through
// V4L2 controls (v4l2-ctl). Automatic adjustments between shots are the main
// cause of flicker in stop motion, and most UVC webcams do not expose these
// modes through QtMultimedia.
class CameraControl : public QObject
{
    Q_OBJECT
    Q_PROPERTY(bool available READ available CONSTANT)

public:
    using QObject::QObject;

    bool available() const;

    // Returns a human readable list of what was changed, empty if nothing.
    Q_INVOKABLE QString setManual(const QCameraDevice &device, bool manual);
};
