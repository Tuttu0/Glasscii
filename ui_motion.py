from PySide6.QtCore import (Qt,QObject,QEvent,QPointF,QRect,QTimer,QPropertyAnimation,
    QParallelAnimationGroup,QEasingCurve)
from PySide6.QtGui import QPainter,QColor,QRadialGradient,QPalette,QFont,QBrush
from PySide6.QtWidgets import QApplication,QWidget,QComboBox,QFontComboBox,QStyledItemDelegate


class DarkItemDelegate(QStyledItemDelegate):
    def __init__(self,parent=None,font_preview=False):
        super().__init__(parent);self.font_preview=font_preview

    def sizeHint(self,option,index):
        size=super().sizeHint(option,index)
        size.setHeight(max(24,size.height()+8))
        return size

    def initStyleOption(self,option,index):
        super().initStyleOption(option,index)
        option.backgroundBrush=QBrush(QColor('#000000'))
        for role,color in [(QPalette.ColorRole.Text,'#ffffff'),(QPalette.ColorRole.WindowText,'#ffffff'),
                           (QPalette.ColorRole.Base,'#000000'),(QPalette.ColorRole.Highlight,'#252525'),
                           (QPalette.ColorRole.HighlightedText,'#ffffff')]:
            option.palette.setColor(role,QColor(color))
        if self.font_preview:
            font=QFont(str(index.data(Qt.ItemDataRole.DisplayRole)))
            font.setPointSize(11);option.font=font


class PopupMotion:
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.popup_animation=None
        self.popup_target=None
        self.setItemDelegate(DarkItemDelegate(self,font_preview=isinstance(self,QFontComboBox)))

    def showPopup(self):
        view=self.view()
        palette=view.palette()
        for role,color in [(QPalette.ColorRole.Base,'#000000'),(QPalette.ColorRole.Window,'#000000'),
                           (QPalette.ColorRole.Text,'#ffffff'),(QPalette.ColorRole.WindowText,'#ffffff'),
                           (QPalette.ColorRole.Highlight,'#252525'),(QPalette.ColorRole.HighlightedText,'#ffffff'),
                           (QPalette.ColorRole.Button,'#000000'),(QPalette.ColorRole.ButtonText,'#ffffff')]:
            palette.setColor(role,QColor(color))
        view.setPalette(palette);view.viewport().setPalette(palette)
        view.setStyleSheet('QAbstractItemView {background:#000;color:#fff;selection-background-color:#252525;selection-color:#fff;outline:0;} QAbstractItemView::item {color:#fff;}')
        super().showPopup()
        popup=self.view().window()
        if popup is self.window() or not popup.isVisible():return
        popup.setObjectName('darkPopup')
        popup.setPalette(palette)
        popup.setStyleSheet('QWidget#darkPopup {background:#000;color:#fff;border:1px solid #444;} QWidget#darkPopup QWidget {background:#000;color:#fff;} QAbstractItemView {background:#000;color:#fff;selection-background-color:#252525;selection-color:#fff;} QAbstractItemView::item:selected {background:#252525;color:#fff;}')
        if self.popup_animation is not None:
            self.popup_animation.stop();self.popup_animation.deleteLater()
        target=QRect(popup.geometry())
        row_height=max(24,view.sizeHintForRow(0))
        desired=row_height*min(self.count(),self.maxVisibleItems())+28
        available=self.screen().availableGeometry()
        target.setHeight(min(max(target.height(),desired),available.height()-8))
        if target.bottom()>available.bottom():target.moveBottom(available.bottom())
        if target.top()<available.top():target.moveTop(available.top())
        self.popup_target=target
        upward=target.center().y()<self.mapToGlobal(self.rect().center()).y()
        start=QRect(target.x(),target.bottom()-11 if upward else target.y(),target.width(),12)
        group=QParallelAnimationGroup(self)
        geometry=QPropertyAnimation(popup,b'geometry',group)
        geometry.setDuration(160);geometry.setStartValue(start);geometry.setEndValue(target)
        geometry.setEasingCurve(QEasingCurve.Type.OutCubic)
        opacity=QPropertyAnimation(popup,b'windowOpacity',group)
        opacity.setDuration(140);opacity.setStartValue(.15);opacity.setEndValue(1.)
        opacity.setEasingCurve(QEasingCurve.Type.OutCubic)
        group.addAnimation(geometry);group.addAnimation(opacity)
        popup.setGeometry(start);popup.setWindowOpacity(.15)
        self.popup_animation=group
        group.start()

    def hidePopup(self):
        if self.popup_animation is not None:self.popup_animation.stop()
        popup=self.view().window()
        if popup is not self.window():
            if self.popup_target is not None:popup.setGeometry(self.popup_target)
            popup.setWindowOpacity(1.)
        super().hidePopup()


class AnimatedComboBox(PopupMotion,QComboBox):pass
class AnimatedFontComboBox(PopupMotion,QFontComboBox):pass


class MouseSurface(QWidget):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.glow_position=None
        self.glow_strength=0.

    def set_glow(self,position,strength):
        self.glow_position=position;self.glow_strength=strength
        self.update()

    def paintEvent(self,event):
        painter=QPainter(self)
        painter.fillRect(self.rect(),Qt.GlobalColor.black)
        painter.fillRect(self.rect(),QColor('#202020'))


class SurfaceMotion(QObject):
    def __init__(self,window,surfaces):
        super().__init__(window)
        self.window=window;self.surfaces=surfaces
        self.position=None;self.target=None;self.strength=0.
        self.timer=QTimer(self);self.timer.setInterval(33);self.timer.timeout.connect(self.tick)
        self.app=QApplication.instance();self.app.installEventFilter(self)
        window.setMouseTracking(True)
        for surface in surfaces:
            surface.setMouseTracking(True)
            for child in surface.findChildren(QWidget):child.setMouseTracking(True)

    def follow(self,point):
        self.target=QPointF(point)
        if self.position is None:self.position=QPointF(point)
        if not self.timer.isActive():self.timer.start()

    def fade(self):
        self.target=None
        if self.strength>.002 and not self.timer.isActive():self.timer.start()

    def eventFilter(self,watched,event):
        if not self.window.isVisible():return False
        if event.type()==QEvent.Type.MouseMove and isinstance(watched,QWidget) and watched.window() is self.window:
            self.follow(event.globalPosition())
        elif watched is self.window and event.type() in (QEvent.Type.Leave,QEvent.Type.WindowDeactivate,QEvent.Type.Hide):
            self.fade()
        return False

    def tick(self):
        if not self.window.isVisible():self.fade()
        wanted=1. if self.target is not None else 0.
        self.strength+=(wanted-self.strength)*.24
        distance=0.
        if self.target is not None:
            delta=self.target-self.position;self.position+=delta*.35
            distance=abs(delta.x())+abs(delta.y())
        for surface in self.surfaces:
            position=QPointF(surface.mapFromGlobal(self.position.toPoint())) if self.position is not None else None
            surface.set_glow(position,self.strength)
        if abs(wanted-self.strength)<.004 and distance<.2:
            self.strength=wanted
            self.timer.stop()
            for surface in self.surfaces:
                position=QPointF(surface.mapFromGlobal(self.position.toPoint())) if wanted else None
                surface.set_glow(position,wanted)

    def stop(self):
        self.timer.stop();self.app.removeEventFilter(self)
        for surface in self.surfaces:surface.set_glow(None,0.)


def install_surface_motion(controller,surfaces):
    controller.ui_motion=SurfaceMotion(controller,surfaces)
