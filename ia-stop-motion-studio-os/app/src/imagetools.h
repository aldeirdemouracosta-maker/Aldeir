#pragma once

#include <QColor>
#include <QImage>

// Pixel operations used by the "IA Local" tools. All functions are pure and
// thread-safe so they can run in a worker thread.
namespace ImageTools {

// Mask weights in [0,1] from a painted mask image (any colour; alpha or
// brightness marks the area), scaled to `size` and feathered by `feather` px.
QVector<float> maskWeights(const QImage &mask, const QSize &size, int feather);

// Replaces the masked area with the same area of a clean plate (a photo of
// the set without puppet or rig) — the classic way to remove rigs and wires.
QImage cleanWithPlate(const QImage &frame, const QImage &plate, const QImage &mask, int feather);

// Fills the masked area from its surroundings (multi-scale diffusion). Good
// for thin wires and small supports when there is no clean plate.
QImage fillMasked(const QImage &frame, const QImage &mask);

struct ChromaOptions {
    QColor key = QColor(0, 177, 64);
    double tolerance = 0.18; // chroma distance fully keyed out (0..1)
    double softness = 0.10;  // extra distance for the soft edge
    bool spill = true;       // remove green/blue light spill on the puppet
};

// Keys out a green/blue screen and composites over `background` (cropped to
// fill). With a null background the result keeps an alpha channel.
QImage chromaKey(const QImage &frame, const ChromaOptions &options, const QImage &background);

} // namespace ImageTools
