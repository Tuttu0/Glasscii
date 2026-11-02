from bisect import bisect_left
from collections import OrderedDict
from threading import local
import math
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QColor, QPainter, QFont, QFontMetricsF, QImage, QStaticText, QTransform, QPolygonF
from engine import luminance, dot_radius


DEFAULT_CHARACTERS = ' .:-=+*#%@'

def normalize_characters(characters):
    cleaned = ''.join(dict.fromkeys(c for c in characters if c.isprintable()))[:128]
    return cleaned if cleaned.strip() else DEFAULT_CHARACTERS


_palette_local=local()

def ascii_palette(characters=DEFAULT_CHARACTERS):
    # QStaticText/font engine caches must not outlive or cross their rendering thread.
    characters=normalize_characters(characters)
    if not hasattr(_palette_local,'cache'):_palette_local.cache=OrderedDict()
    cache=_palette_local.cache
    if characters not in cache:
        cache[characters]=_build_ascii_palette(characters)
        if len(cache)>8:cache.popitem(last=False)
    cache.move_to_end(characters)
    return cache[characters]


def _build_ascii_palette(characters):
    font = QFont('Consolas')
    font.setStyleHint(QFont.StyleHint.Monospace)
    font.setPixelSize(16)
    metrics = QFontMetricsF(font)
    # Measured ink coverage, rather than an assumed density order of symbols.
    candidates = normalize_characters(characters)
    entries = []
    for char in dict.fromkeys(candidates):
        tile = QImage(10, 20, QImage.Format.Format_ARGB32_Premultiplied)
        tile.fill(Qt.GlobalColor.transparent)
        painter = QPainter(tile)
        painter.setFont(font)
        painter.setPen(Qt.GlobalColor.white)
        text = QStaticText(char)
        text.setTextFormat(Qt.TextFormat.PlainText)
        text.prepare(QTransform(), font)
        offset = QPointF((10 - text.size().width()) / 2, (20 - metrics.height()) / 2)
        painter.drawStaticText(offset, text)
        painter.end()
        coverage = sum(bytes(tile.constBits())[3::4]) / (255 * 200)
        entries.append((coverage, text, offset))
    entries.sort(key=lambda item: item[0])
    values = [entry[0] for entry in entries]
    maximum = max(values) or 1
    lookup = []
    for value in range(256):
        target = value / 255 * maximum
        index = min(len(values) - 1, bisect_left(values, target))
        if index and abs(values[index - 1] - target) < abs(values[index] - target):
            index -= 1
        lookup.append(entries[index][1:])
    return font, lookup


def tone_lut(brightness=100, highlights=0, black_point=0):
    """Identity at defaults; black point remaps the low end, highlights use a bright-tone mask."""
    floor = max(0.,min(.8,black_point/100))
    table=[]
    for channel in range(256):
        value=max(0.,min(1.,channel/255*brightness/100))
        value=max(0.,(value-floor)/(1-floor))
        mask=max(0.,(value-.45)/.55)**2
        if highlights>=0:
            value+=highlights/100*mask*(1-value)
        elif value>.45:
            t=(value-.45)/.55
            value=.45+.55*t/(1+(-highlights/100)*1.5*t)
        table.append(max(0,min(255,round(value*255))))
    return table


def rasterize(frame, mode, colored, paper, characters=DEFAULT_CHARACTERS, brightness=100, invert=False, highlights=0, black_point=0):
    cw, ch = (10, 20) if mode == 'ASCII' else (9, 9)
    image = QImage(frame.width * cw, frame.height * ch, QImage.Format.Format_ARGB32_Premultiplied)
    if image.isNull():
        raise MemoryError('Not enough memory for this detail level. Try fewer columns.')
    image.fill({'Transparent': Qt.GlobalColor.transparent,
                'Black': QColor('#080a0e'), 'White': QColor('#fafafa')}[paper])
    lut=tone_lut(brightness,highlights,black_point)
    painter = QPainter(image)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if mode == 'ASCII':
            font, lookup = ascii_palette(normalize_characters(characters))
            painter.setFont(font)
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        for index, pixel in enumerate(frame.pixels):
            r, g, b, alpha = pixel
            if alpha == 0:
                continue
            x, y = index % frame.width * cw, index // frame.width * ch
            r,g,b = lut[r],lut[g],lut[b]
            adjusted = (r, g, b, alpha)
            gray = round(luminance(adjusted))
            color = QColor(r, g, b, alpha) if colored else QColor(gray, gray, gray, alpha)
            color.setAlpha(alpha)
            if mode == 'ASCII':
                level = lut[frame.levels[index] if frame.levels else round(luminance(pixel))] / 255
                # RGB already carries brightness; avoid suppressing dark details twice.
                level = .30 + .70 * math.sqrt(level)
                if invert:
                    level = 1 - level
                text, offset = lookup[max(0, min(255, round(level * 255)))]
                painter.setPen(color)
                painter.drawStaticText(QPointF(x, y) + offset, text)
            else:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(color)
                radius = dot_radius(adjusted,cw,invert)
                cx,cy=x+cw/2,y+ch/2
                if mode=='Halftone':
                    painter.drawEllipse(QRectF(cx-radius,cy-radius,radius*2,radius*2))
                elif mode=='Diamonds':
                    painter.drawPolygon(QPolygonF([QPointF(cx,cy-radius),QPointF(cx+radius,cy),
                                                   QPointF(cx,cy+radius),QPointF(cx-radius,cy)]))
                elif mode=='Voxels':
                    # Isometric cube silhouette within each square cell: top + two shaded faces.
                    depth=gray/255 if invert else 1-gray/255
                    half=cw*(.30+.17*depth)
                    a=QPointF(cx,cy-half)
                    b=QPointF(cx+half,cy-half*.5)
                    c=QPointF(cx,cy)
                    d=QPointF(cx-half,cy-half*.5)
                    e=QPointF(cx-half,cy+half*.5)
                    f=QPointF(cx,cy+half)
                    g=QPointF(cx+half,cy+half*.5)
                    for shade,points in [(color.lighter(125),[a,b,c,d]),
                                         (color.darker(115),[d,c,f,e]),
                                         (color.darker(150),[c,b,g,f])]:
                        painter.setBrush(shade)
                        painter.drawPolygon(QPolygonF(points))
                else:
                    raise ValueError('Unknown drawing style')

    finally:
        painter.end()
    return image
