import math
from PySide6.QtCore import Qt, QRectF, QPointF, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath
from PySide6.QtWidgets import QWidget


class ArtCanvas(QWidget):
    def __init__(self, interactive=False):
        super().__init__()
        self.image = None
        self.interactive = interactive  # Preview backdrop, not pan/zoom permission.
        self.columns = self.rows = 0
        self.paper = 'Transparent'
        self.pointer = None
        self.pointer_target = None
        self.strength = 40.
        self.effect_timer = QTimer(self)
        self.effect_timer.setInterval(15)
        self.effect_timer.timeout.connect(self.tick)
        self._fitting_preview=False
        self.fit_timer=QTimer(self)
        self.fit_timer.setSingleShot(True)
        self.fit_timer.timeout.connect(self.fit_preview_height)
        self.setMinimumSize(140, 120)
        if interactive:
            self.setMouseTracking(True)
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            # Desktop window receives mouse events, so dragging still moves the window.
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def set_art(self, image, columns, rows, paper):
        self.image, self.columns, self.rows, self.paper = image, columns, rows, paper
        self.request_preview_fit()
        self.update()

    def request_preview_fit(self):
        if self.interactive and not self.fit_timer.isActive():
            self.fit_timer.start(0)

    def fit_preview_height(self):
        # Never change this widget's geometry from inside resizeEvent.
        if self._fitting_preview or not self.interactive or self.image is None:
            return
        if self.image.width()<=0:
            return
        self._fitting_preview=True
        try:
            wanted=max(1,min(260,round(self.width()*self.image.height()/self.image.width())))
            if self.minimumHeight()!=wanted or self.maximumHeight()!=wanted:
                self.setFixedHeight(wanted)
        finally:
            self._fitting_preview=False

    def resizeEvent(self,event):
        super().resizeEvent(event)
        self.request_preview_fit()

    def effect_at(self, point):
        if self.image is None or not self.rect().contains(point.toPoint()):
            self.clear_effect()
            return
        self.pointer_target = QPointF(point)
        if self.pointer is None:
            self.pointer = QPointF(point)
        if not self.effect_timer.isActive(): self.effect_timer.start()

    def clear_effect(self):
        self.pointer_target = None
        if self.strength > .001 and not self.effect_timer.isActive(): self.effect_timer.start()

    def tick(self):
        wanted = 3. if self.pointer_target is not None else 0.
        self.strength += (wanted - self.strength) * .38
        distance = 0.
        if self.pointer_target is not None:
            delta = self.pointer_target - self.pointer
            self.pointer += delta * .45
            distance = abs(delta.x()) + abs(delta.y())
        self.update()
        if abs(self.strength - wanted) < .004 and distance < .2:
            self.strength = wanted
            if not wanted: self.pointer = None
            self.effect_timer.stop()
            self.update()

    def leaveEvent(self,event):
        self.clear_effect()
        super().leaveEvent(event)

    def mouseMoveEvent(self, event):
        if self.interactive: self.effect_at(event.position())

    def wheelEvent(self, event):
        event.accept()

    def target_rect(self):
        if self.image is None: return QRectF()
        fitted = self.image.size().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
        return QRectF((self.width()-fitted.width())/2, (self.height()-fitted.height())/2,
                      fitted.width(), fitted.height())

    def draw_art(self, painter, target):
        if (self.pointer is None or self.strength < .002 or not self.columns or not self.rows
                or not target.contains(self.pointer)):
            painter.drawImage(target, self.image)
            return
        cell_w, cell_h = target.width()/self.columns, target.height()/self.rows
        radius = min(48., max(14., cell_w*9))
        reach = radius + 7
        left = max(0, int((self.pointer.x()-reach-target.x())/cell_w))
        right = min(self.columns-1, int((self.pointer.x()+reach-target.x())/cell_w))
        top = max(0, int((self.pointer.y()-reach-target.y())/cell_h))
        bottom = min(self.rows-1, int((self.pointer.y()+reach-target.y())/cell_h))
        area = QRectF(target.x()+left*cell_w, target.y()+top*cell_h,
                      (right-left+1)*cell_w, (bottom-top+1)*cell_h)
        # Paint the original everywhere except the small cell-aligned interaction region.
        whole, hole = QPainterPath(), QPainterPath()
        whole.addRect(target); hole.addRect(area)
        painter.save()
        painter.setClipPath(whole.subtracted(hole), Qt.ClipOperation.IntersectClip)
        painter.drawImage(target, self.image)
        painter.restore()
        if self.paper != 'Transparent':
            painter.fillRect(area, QColor('#080a0e' if self.paper=='Black' else '#fafafa'))
        source_w, source_h = self.image.width()/self.columns, self.image.height()/self.rows
        painter.save()
        painter.setClipRect(target, Qt.ClipOperation.IntersectClip)
        for row in range(top,bottom+1):
            for column in range(left,right+1):
                destination = QRectF(target.x()+column*cell_w, target.y()+row*cell_h, cell_w, cell_h)
                delta = destination.center()-self.pointer
                distance = math.hypot(delta.x(),delta.y())
                if distance < radius:
                    force = 6 * self.strength * (1-distance/radius)**2
                    direction = delta / distance if distance > .1 else QPointF(1,0)
                    destination.translate(direction*force)
                source = QRectF(column*source_w,row*source_h,source_w,source_h)
                painter.drawImage(destination,self.image,source)
        painter.restore()

    def paintEvent(self,event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.interactive:
            painter.fillRect(self.rect(),Qt.GlobalColor.black)
        if self.image is None:
            painter.setPen(QColor('#F7F2EB'))
            painter.drawText(self.rect(),Qt.AlignmentFlag.AlignCenter,'Drop an image or GIF here')
        else:
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            self.draw_art(painter,self.target_rect())
