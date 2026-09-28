#pragma once

#include <QColor>
#include <QImage>
#include <QSize>
#include <QString>

// Draws a title as a full-frame transparent image. The same PNG is used by
// the preview monitor and by the MLT render, so what you see is what you get.
namespace TitleRenderer {

QImage render(const QString &text, const QSize &frameSize, const QString &position,
              int sizePercent, const QColor &color, bool box);

}
