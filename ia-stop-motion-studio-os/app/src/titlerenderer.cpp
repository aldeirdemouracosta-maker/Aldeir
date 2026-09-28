#include "titlerenderer.h"

#include <QFont>
#include <QFontMetricsF>
#include <QPainter>
#include <QPainterPath>

QImage TitleRenderer::render(const QString &text, const QSize &frameSize, const QString &position,
                             int sizePercent, const QColor &color, bool box)
{
    QImage image(frameSize, QImage::Format_ARGB32_Premultiplied);
    image.fill(Qt::transparent);
    if (text.trimmed().isEmpty())
        return image;

    QPainter p(&image);
    p.setRenderHint(QPainter::Antialiasing);
    p.setRenderHint(QPainter::TextAntialiasing);

    QFont font(QStringLiteral("DejaVu Sans"));
    font.setBold(true);
    font.setPixelSize(qMax(8, frameSize.height() * sizePercent / 100));
    const QFontMetricsF fm(font);

    const QStringList lines = text.split(QLatin1Char('\n'));
    const double lineHeight = fm.lineSpacing();
    double textWidth = 0;
    for (const QString &line : lines)
        textWidth = qMax(textWidth, fm.horizontalAdvance(line));
    const double textHeight = lineHeight * lines.size();

    const double margin = frameSize.height() * 0.07;
    double top;
    if (position == QLatin1String("top"))
        top = margin;
    else if (position == QLatin1String("center"))
        top = (frameSize.height() - textHeight) / 2;
    else
        top = frameSize.height() - margin - textHeight;

    if (box) {
        const double pad = font.pixelSize() * 0.4;
        const QRectF band((frameSize.width() - textWidth) / 2 - pad * 1.5, top - pad,
                          textWidth + pad * 3, textHeight + pad * 2);
        p.setPen(Qt::NoPen);
        p.setBrush(QColor(0, 0, 0, 150));
        p.drawRoundedRect(band, pad, pad);
    }

    QPainterPath path;
    for (int i = 0; i < lines.size(); ++i) {
        const double x = (frameSize.width() - fm.horizontalAdvance(lines.at(i))) / 2;
        path.addText(QPointF(x, top + fm.ascent() + i * lineHeight), font, lines.at(i));
    }
    // Dark outline keeps the text readable over bright felt/fabric colours.
    p.setPen(QPen(QColor(0, 0, 0, 200), qMax(2.0, font.pixelSize() * 0.08), Qt::SolidLine, Qt::RoundCap, Qt::RoundJoin));
    p.setBrush(Qt::NoBrush);
    p.drawPath(path);
    p.setPen(Qt::NoPen);
    p.setBrush(color.isValid() ? color : QColor(Qt::white));
    p.drawPath(path);
    return image;
}
