import sys
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, QEvent, QThread, Signal, QRectF, QSettings, QObject, QRunnable, QThreadPool, QSignalBlocker, QPointF
from PySide6.QtGui import QColor, QPainter, QImage, QLinearGradient, QIcon, QRadialGradient, QCursor
from PySide6.QtWidgets import (
    QApplication, QWidget, QMainWindow, QLabel, QPushButton,
    QFileDialog, QVBoxLayout, QHBoxLayout, QSizeGrip, QSystemTrayIcon, QMenu,
)
from engine import load_clip
from renderer import rasterize, normalize_characters
from ui import ArtCanvas, build_ui, THEME
from windows_effects import apply_glass


class Loader(QThread):
    done = Signal(object, str)

    def __init__(self, path, cell_size, mode, style, viewport):
        super().__init__()
        self.path, self.cell_size, self.mode, self.style = path, cell_size, mode, style
        self.viewport = viewport

    def run(self):
        try:
            clip = load_clip(self.path, mode=self.mode, cell_size=self.cell_size, viewport=self.viewport)
            first = rasterize(clip.frames[0], self.mode, *self.style)
            self.done.emit((clip, first), '')
        except Exception as exc:
            self.done.emit(None, str(exc))


class RenderSignals(QObject):
    done = Signal(object)


class RenderJob(QRunnable):
    def __init__(self, token, index, frame, mode, style):
        super().__init__()
        self.token, self.index, self.frame = token, index, frame
        self.mode, self.style = mode, style
        self.signals = RenderSignals()

    def run(self):
        try:
            image = rasterize(self.frame, self.mode, *self.style)
            self.signals.done.emit((self.token, self.index, image, ''))
        except Exception as exc:
            self.signals.done.emit((self.token, self.index, None, str(exc)))


class GlassWidget(QWidget):
    resized = Signal()
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.setWindowTitle('· Glasscii')
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAutoFillBackground(False)
        self.resize(440, 340)
        self.setMouseTracking(True)
        self.hovered = False
        self.mouse_pos = None
        self.setMinimumSize(220, 200)
        self.drag_offset = None
        self.tint = 12
        self.locked = False
        self.frame_hidden=False
        self.canvas = ArtCanvas()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 12)
        self.frame_controls=QWidget()
        frame_policy=self.frame_controls.sizePolicy()
        frame_policy.setRetainSizeWhenHidden(True)
        self.frame_controls.setSizePolicy(frame_policy)
        bar = QHBoxLayout(self.frame_controls);bar.setContentsMargins(0,0,0,0)
        title = QLabel('Glasscii')
        self.title=title
        title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        title.setStyleSheet('color: #c0c0c0; font-size: 10px; letter-spacing: 2px;')
        bar.addWidget(title)
        bar.addStretch()
        for label, action in [('⚙', controller.reveal), ('×', self.close)]:
            button = QPushButton(label)
            button.setFixedSize(27, 25)
            button.setStyleSheet('QPushButton {color:#bbbbbb;background:rgba(255,255,255,45);border:0;border-radius:6px;} QPushButton:hover {color:#000000;background:#ffffff;} QPushButton:pressed {background:#dddddd;}')
            button.clicked.connect(action)
            bar.addWidget(button)
        layout.addWidget(self.frame_controls)
        layout.addWidget(self.canvas, 1)
        bottom = QHBoxLayout()
        bottom.addStretch()
        self.grip = QSizeGrip(self)
        grip_policy=self.grip.sizePolicy()
        grip_policy.setRetainSizeWhenHidden(True)
        self.grip.setSizePolicy(grip_policy)
        bottom.addWidget(self.grip)
        layout.addLayout(bottom)
        self._applying_frame=False
        self._applied_frame_hidden=False
        self._applying_effect=False
        self._last_effect=None
        self._last_reported_size=None
        self._stopped_updates=False
        self._last_cursor=None
        self.cursor_timer=QTimer(self)
        self.cursor_timer.setInterval(16)
        self.cursor_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.cursor_timer.timeout.connect(self.poll_cursor)
        self.frame_timer=QTimer(self)
        self.frame_timer.setSingleShot(True)
        self.frame_timer.timeout.connect(self._apply_frame_hidden)
        self.resize_timer=QTimer(self)
        self.resize_timer.setSingleShot(True)
        self.resize_timer.timeout.connect(self._emit_resized)
        self.effect_timer=QTimer(self)
        self.effect_timer.setSingleShot(True)
        self.effect_timer.timeout.connect(self._apply_effect)

    def showEvent(self, event):
        super().showEvent(event)
        self.request_effect_update()
        self.cursor_timer.start()
        self.notify_visibility()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        p.fillRect(self.rect(), Qt.GlobalColor.transparent)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        if self.frame_hidden:return
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
        gradient.setColorAt(0, QColor(255, 255, 255, self.tint))
        gradient.setColorAt(1, QColor(255, 255, 255, self.tint))
        p.setBrush(gradient)
        p.setPen(QColor(255, 255, 255, 210 if self.hovered else 120))
        p.drawRoundedRect(rect, 18, 18)
        if self.mouse_pos is not None and self.hovered:
            glow = QRadialGradient(self.mouse_pos, 130)
            glow.setColorAt(0, QColor(255, 255, 255, 23))
            glow.setColorAt(1, QColor(255, 255, 255, 0))
            p.setBrush(glow)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(rect, 18, 18)

    def set_frame_hidden(self,hidden):
        hidden=bool(hidden)
        self.frame_hidden=hidden
        if self._stopped_updates:
            return
        if self._applied_frame_hidden==hidden and not self._applying_frame:
            return
        self.frame_timer.start(0)

    def _apply_frame_hidden(self):
        if self._stopped_updates or self._applying_frame:
            return
        hidden=self.frame_hidden
        self._applying_frame=True
        try:
            self.frame_controls.setVisible(not hidden)
            self.grip.setVisible(not hidden and not self.locked)
            # Visibility only: preserve margins and occupied layout space, so
            # hiding chrome cannot resize the canvas or start a reload loop.
            self._applied_frame_hidden=hidden
            self.update()
        finally:
            self._applying_frame=False
        self.request_effect_update()
        if self.frame_hidden!=hidden:
            self.frame_timer.start(0)

    def queue_resize_notification(self):
        if hasattr(self,'resize_timer') and not self._stopped_updates:
            self.resize_timer.start(0)

    def _emit_resized(self):
        if self._stopped_updates:
            return
        viewport=(self.canvas.width(),self.canvas.height())
        if viewport!=self._last_reported_size:
            self._last_reported_size=viewport
            self.resized.emit()

    def request_effect_update(self):
        if (hasattr(self,'effect_timer') and not self._stopped_updates
                and not self._applying_effect):
            self.effect_timer.start(0)

    def _apply_effect(self):
        if self._stopped_updates or self._applying_effect or not self.isVisible():
            return
        signature=(int(self.winId()),self.controller.frosted.isChecked() and not self.frame_hidden)
        if signature==self._last_effect:
            return
        self._applying_effect=True
        try:
            self._last_effect=signature
            message=apply_glass(*signature)
            self.controller.effect_label.setText(message)
        finally:
            self._applying_effect=False

    def stop_updates(self):
        self._stopped_updates=True
        self.frame_timer.stop()
        self.resize_timer.stop()
        self.effect_timer.stop()
        self.cursor_timer.stop()

    def contextMenuEvent(self,event):
        menu=QMenu(self)
        menu.addAction('Settings',self.controller.reveal)
        menu.addAction('Show frame' if self.frame_hidden else 'Hide frame',
                       lambda:self.controller.hide_frame.setChecked(not self.frame_hidden))
        if self.controller.manager:
            menu.addAction('Rename widget',lambda:self.controller.manager.rename_widget(self.controller.session_id))
        menu.addAction('Hide widget',self.close)
        menu.exec(event.globalPos())

    def mouseDoubleClickEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:self.controller.reveal()

    def notify_visibility(self):
        if hasattr(self.controller,'timer'):QTimer.singleShot(0,self.controller.schedule)

    def hideEvent(self,event):
        self.cursor_timer.stop()
        self.canvas.clear_effect()
        super().hideEvent(event);self.notify_visibility()

    def changeEvent(self,event):
        super().changeEvent(event)
        if event.type()==QEvent.Type.WindowStateChange:self.notify_visibility()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.queue_resize_notification()

    def poll_cursor(self):
        if self._stopped_updates or not self.isVisible() or self.isMinimized():return
        global_position=QCursor.pos()
        position=self.mapFromGlobal(global_position)
        inside=self.rect().contains(position)
        marker=(position.x(),position.y(),inside)
        if marker==self._last_cursor:return
        self._last_cursor=marker
        was_hovered=self.hovered
        self.hovered=inside
        self.mouse_pos=QPointF(position) if inside else None
        canvas_position=QPointF(self.canvas.mapFromGlobal(global_position))
        if inside and self.drag_offset is None:
            self.canvas.effect_at(canvas_position)
        else:
            self.canvas.clear_effect()
        if inside or was_hovered:self.update()

    def enterEvent(self, event):
        self._last_cursor=None
        self.poll_cursor()
        super().enterEvent(event)

    def leaveEvent(self, event):
        # A zero-alpha pixel can cause native leave events even though the cursor
        # is still inside the widget. Poll coordinates instead of resetting it.
        self._last_cursor=None
        self.poll_cursor()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and not self.locked:
            self.drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        # Painting is capped by cursor_timer; high-rate mice must not drive it.
        if self.drag_offset is not None and not self.locked:
            self.move(event.globalPosition().toPoint()-self.drag_offset)

    def mouseReleaseEvent(self, event):
        self.drag_offset = None
        self._last_cursor=None

    def closeEvent(self, event):
        self.controller.settings.setValue('widget_geometry', self.saveGeometry())
        self.controller.reveal()
        super().closeEvent(event)


class Controller(QMainWindow):
    kind = 'image'
    def __init__(self, manager=None, session_id=None, autoload=True):
        super().__init__()
        self.manager, self.session_id = manager, session_id
        self.settings = QSettings('Glasscii', 'Desktop')
        if manager is not None:
            self.settings.beginGroup(f'profiles/{session_id}')
        self.settings.setValue('widget_type','image')
        if self.settings.value('ui_version') is None:
            if not self.settings.contains('tint'): self.settings.setValue('tint', 12)
            if not self.settings.contains('paper'): self.settings.setValue('paper', 'Transparent')
            self.settings.setValue('ui_version', '4')
        self.display_name=str(self.settings.value('widget_name','')).strip()
        self.applying_preset=False
        self.path = ''
        self.clip = None
        self.index = self.repeats = 0
        self.cache = {}  # Bounded raster cache, not all full-size animation frames.
        self.loader = None
        self.closing = False
        self.active_mode = 'ASCII'
        self.committed_path = ''
        self.committed_cell_size = 4
        self.reload_pending = False
        self.animation_finished = False
        self.generation = 0
        self.render_busy = False
        self.pending_render = None
        self.render_job = None
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        build_ui(self)
        self.widget = GlassWidget(self)
        self.widget.tint = self.tint.value()
        self.widget.set_frame_hidden(self.hide_frame.isChecked())
        self.hide_frame.toggled.connect(self.widget.set_frame_hidden)
        self.restore_widget = autoload and str(self.settings.value('widget_visible','false')).lower() in ('true','1')
        geometry = self.settings.value('widget_geometry')
        if geometry:
            self.widget.restoreGeometry(geometry)
        self.show_button.clicked.connect(self.show_widget)
        self.top.toggled.connect(self.change_top)
        self.lock.toggled.connect(self.change_lock)
        self.tint.valueChanged.connect(self.change_tint)
        self.frosted.toggled.connect(self.change_glass)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.advance)
        self.debounce = QTimer(self)
        self.debounce.setSingleShot(True)
        self.debounce.setInterval(250)
        self.debounce.timeout.connect(self.reload)
        self.mode.currentTextChanged.connect(self.queue_reload)
        self.cell_size.valueChanged.connect(self.queue_reload)
        self.widget.resized.connect(self.queue_reload)
        self.style_debounce = QTimer(self)
        self.style_debounce.setSingleShot(True)
        self.style_debounce.setInterval(180)
        self.style_debounce.timeout.connect(self.refresh_style)
        self.characters.textChanged.connect(lambda _: self.style_debounce.start())
        for signal in (self.color.currentTextChanged, self.paper.currentTextChanged, self.invert.toggled):
            signal.connect(self.refresh_style)
        self.characters.setEnabled(self.mode.currentText() == 'ASCII')
        self.reset_characters.setEnabled(self.mode.currentText() == 'ASCII')
        for control in (self.brightness,self.highlights,self.black_point):
            control.valueChanged.connect(lambda _: self.style_debounce.start())
        if manager is not None:
            manager.bind_controls(self)
        else:
            self.widget_picker.addItem('1 · Widget')
            self.add_widget_button.setEnabled(False)
            self.remove_widget_button.setEnabled(False)
            self.rename_widget_button.setEnabled(False)
        self.speed.valueChanged.connect(self.schedule)
        self.setAcceptDrops(True)
        self.tray = None
        if manager is None and QSystemTrayIcon.isSystemTrayAvailable():
            icon_image = QImage(32, 32, QImage.Format.Format_ARGB32)
            icon_image.fill(QColor('#ffffff'))
            from PySide6.QtGui import QPixmap
            self.tray = QSystemTrayIcon(QIcon(QPixmap.fromImage(icon_image)), self)
            menu = QMenu(self)
            menu.addAction('Settings', self.reveal)
            menu.addAction('Show widget', self.show_widget)
            menu.addAction('Quit', self.quit)
            self.tray.setContextMenu(menu)
            self.tray.setToolTip('Glasscii — right click for settings or Quit')
            self.tray.show()
        last = self.settings.value('last_file', '')
        if autoload and last and Path(last).is_file():
            self.path = last
            QTimer.singleShot(0, self.reload)

    def reveal(self):
        if self.manager is not None:
            self.manager.select(self.session_id)
            return
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def choose(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Choose image / GIF', '',
                                              'Images (*.png *.jpg *.jpeg *.gif *.webp *.bmp)')
        if path:
            self.open_path(path)

    def open_path(self, path):
        if self.loader is not None:
            return
        self.path = path
        with QSignalBlocker(self.cell_size):
            self.cell_size.setMinimum(2)
        self.debounce.stop()
        self.reload()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and self.loader is None:
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls and urls[0].isLocalFile():
            self.open_path(urls[0].toLocalFile())

    def queue_reload(self, *_):
        if self.applying_preset:return
        if self.mode.currentText() != self.active_mode:
            with QSignalBlocker(self.cell_size):
                self.cell_size.setMinimum(2)
        is_ascii = self.mode.currentText() == 'ASCII'
        self.characters.setEnabled(is_ascii and self.loader is None)
        self.reset_characters.setEnabled(is_ascii and self.loader is None)
        self.timer.stop()
        if self.path:
            if self.loader is not None:
                self.reload_pending = True
            else:
                self.debounce.start()

    def style_values(self):
        return (self.color.currentText() == 'Original colors', self.paper.currentText(),
                normalize_characters(self.characters.text()), self.brightness.value(), self.invert.isChecked(),
                self.highlights.value(), self.black_point.value())

    def reload(self):
        if self.closing or not self.path or self.loader is not None:
            return
        self.timer.stop()
        self.status.setText('Updating detail… keeping the previous image until the new result is ready.')
        # Loading and its first raster form a transaction; errors never clear the old image.
        for control in (self.open_button, self.mode, self.cell_size, self.color, self.paper, self.characters, self.reset_characters, self.brightness, self.invert, self.highlights, self.black_point, self.presets, self.reset_adjustments_button):
            control.setEnabled(False)
        self.widget.layout().activate()
        viewport = (self.widget.canvas.width(), self.widget.canvas.height())
        self.loader = Loader(self.path, self.cell_size.value(), self.mode.currentText(), self.style_values(), viewport)
        self.loader.done.connect(self.loaded)
        self.loader.finished.connect(self.worker_finished)
        self.loader.start()

    def loaded(self, result, error):
        if self.closing:
            return
        if error:
            self.path = self.committed_path
            with QSignalBlocker(self.mode), QSignalBlocker(self.cell_size):
                self.mode.setCurrentText(self.active_mode)
                self.cell_size.setRange(self.clip.minimum_cell if self.clip else 2, max(24, self.clip.minimum_cell if self.clip else 2))
                self.cell_size.setValue(self.committed_cell_size)
            self.cell_label.setText(f'{self.cell_size.value()} px')
            self.status.setText('Update skipped; previous image kept. ' + error)
            return
        clip, first = result
        self.generation += 1
        self.pending_render = None
        self.clip = clip
        self.active_mode = clip.mode
        self.committed_path = self.path
        self.committed_cell_size = clip.cell_size
        self.index = self.repeats = 0
        self.animation_finished = False
        with QSignalBlocker(self.cell_size):
            self.cell_size.setRange(clip.minimum_cell, max(24, clip.minimum_cell))
            self.cell_size.setValue(clip.cell_size)
        self.cell_label.setText(f'{clip.cell_size} px')
        self.cache = {0: first}
        self.publish(first)
        # Keep the editor window stable when conversion finishes. Its scroll
        # area handles content changes; a canvas update must not resize it.
        self.file_label.setText(self.fontMetrics().elidedText(Path(self.path).name, Qt.TextElideMode.ElideMiddle, 180))
        self.file_label.setToolTip(self.path)
        self.settings.setValue('last_file', self.path)
        self.status.setText(f'{len(clip.frames)} frame(s) · ready for your desktop')
        if self.manager is not None:
            self.manager.refresh_pickers()
        if self.restore_widget:
            self.restore_widget = False
            QTimer.singleShot(0,self.show_widget)

    def worker_finished(self):
        worker = self.loader
        self.loader = None
        if worker is not None: worker.deleteLater()
        if self.closing: return
        for control in (self.open_button, self.mode, self.cell_size, self.color, self.paper, self.characters, self.reset_characters, self.brightness, self.invert, self.highlights, self.black_point, self.presets, self.reset_adjustments_button):
            control.setEnabled(True)
        is_ascii = self.mode.currentText() == 'ASCII'
        self.characters.setEnabled(is_ascii)
        self.reset_characters.setEnabled(is_ascii)
        if self.reload_pending:
            self.reload_pending = False
            QTimer.singleShot(0, self.reload)
        else:
            self.schedule()

    def refresh_style(self, *_):
        if self.applying_preset:return
        self.generation += 1
        self.cache.clear()
        self.timer.stop()
        self.display_frame()

    def publish(self, image):
        frame = self.clip.frames[self.index]
        self.preview.set_art(image,frame.width,frame.height,self.paper.currentText())
        self.widget.canvas.set_art(image,frame.width,frame.height,self.paper.currentText())

    def display_frame(self):
        if not self.clip or self.closing:
            return
        if self.index in self.cache:
            self.publish(self.cache[self.index])
            self.schedule()
            return
        request = (self.generation, self.index, self.clip.frames[self.index],
                   self.active_mode, self.style_values())
        if self.render_busy:
            self.pending_render = request  # Latest request wins; never grow a queue.
            return
        self.start_render(request)

    def start_render(self, request):
        self.render_busy = True
        self.render_job = RenderJob(*request)
        self.render_job.signals.done.connect(self.rendered)
        self.pool.start(self.render_job)

    def rendered(self, result):
        self.render_busy = False
        token, index, image, error = result
        if self.closing:
            return
        if token == self.generation:
            if error:
                self.status.setText('Rendering skipped; previous image kept. ' + error)
                self.animation_finished = True
            else:
                if len(self.cache) >= 3:
                    self.cache.pop(next(iter(self.cache)))
                self.cache[index] = image
                if index == self.index:
                    self.publish(image)
        pending, self.pending_render = self.pending_render, None
        if pending is not None and pending[0] == self.generation:
            self.start_render(pending)
        else:
            self.schedule()

    def animation_visible(self):
        return (self.isVisible() and not self.isMinimized()) or (self.widget.isVisible() and not self.widget.isMinimized())

    def showEvent(self,event):
        super().showEvent(event)
        if hasattr(self,'timer'):QTimer.singleShot(0,self.schedule)

    def hideEvent(self,event):
        super().hideEvent(event)
        if hasattr(self,'timer'):self.schedule()

    def changeEvent(self,event):
        super().changeEvent(event)
        if event.type()==QEvent.Type.WindowStateChange and hasattr(self,'timer'):self.schedule()

    def reset_adjustments(self):
        if self.loader is not None:return
        self.brightness.setValue(100);self.highlights.setValue(0);self.black_point.setValue(0)
        with QSignalBlocker(self.invert):self.invert.setChecked(False)
        self.style_debounce.stop();self.refresh_style()
        self.status.setText('Adjustments reset · your image and style are unchanged.')

    def schedule(self, *_):
        self.timer.stop()
        if (not self.closing and self.clip and len(self.clip.frames) > 1 and not self.animation_finished
                and self.animation_visible() and not self.debounce.isActive() and self.loader is None and not self.render_busy):
            self.timer.start(max(10, round(self.clip.frames[self.index].duration * 100 / self.speed.value())))

    def advance(self):
        if not self.clip:
            return
        next_index = self.index + 1
        if next_index == len(self.clip.frames):
            loop = self.clip.loop
            if loop is None or (loop != 0 and self.repeats >= loop):
                self.animation_finished = True
                return
            self.repeats += 1
            next_index = 0
        self.index = next_index
        self.display_frame()

    def change_glass(self, *_):
        self.widget.request_effect_update()
        self.widget.update()

    def show_widget(self):
        if not self.clip:
            self.reveal()
            self.status.setText('Choose an image or GIF for this widget first.')
            return
        self.widget.show()
        self.widget.raise_()

    def change_tint(self, value):
        self.widget.tint = value
        self.widget.update()

    def change_top(self, enabled):
        visible = self.widget.isVisible()
        self.widget.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, enabled)
        if visible:
            self.widget.show()

    def change_lock(self, enabled):
        self.widget.locked = enabled
        self.widget.grip.setVisible(not enabled and not self.widget.frame_hidden)
        if enabled:
            self.widget.setFixedSize(self.widget.size())
        else:
            self.widget.setMinimumSize(220, 200)
            self.widget.setMaximumSize(16777215, 16777215)

    def persist(self):
        for key, value in [('hide_frame',self.hide_frame.isChecked()), ('widget_name',self.display_name), ('cell_size', self.cell_size.value()), ('characters', self.characters.text()), ('brightness',self.brightness.value()),
                           ('highlights',self.highlights.value()), ('black_point',self.black_point.value()),
                           ('invert',self.invert.isChecked()), ('widget_visible',self.widget.isVisible()), ('tint', self.tint.value()),
                           ('mode', self.active_mode if self.clip else self.mode.currentText()), ('color', self.color.currentText()),
                           ('paper', self.paper.currentText()), ('widget_geometry', self.widget.saveGeometry())]:
            self.settings.setValue(key, value)
        self.settings.sync()

    def stop(self, persist=True):
        if self.closing: return
        if persist: self.persist()
        self.closing = True
        self.widget.stop_updates()
        self.preview.fit_timer.stop()
        self.ui_motion.stop()
        self.timer.stop()
        self.debounce.stop()
        self.style_debounce.stop()
        if self.loader:
            self.loader.wait()
        self.pool.waitForDone()
        self.preview.effect_timer.stop()
        self.widget.canvas.effect_timer.stop()
        if self.tray: self.tray.hide()

    def quit(self):
        if self.manager is not None:
            self.manager.quit_all()
        else:
            self.stop()
            QApplication.instance().quit()

    def closeEvent(self, event):
        self.persist()
        any_widget = self.widget.isVisible() or (self.manager is not None and any(c.widget.isVisible() for c in self.manager.sessions.values()))
        if any_widget and not self.closing:
            self.hide()
            event.ignore()
        else:
            self.quit()
            event.accept()

def resource_path(name):
    base = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
    return str(base / name)

def main():
    if sys.platform == 'win32':
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            'Glasscii.Desktop'
        )
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    app.setStyleSheet(THEME)
    app.setWindowIcon(QIcon(resource_path('icon.ico')))
    from workspace import Workspace
    app.setQuitOnLastWindowClosed(False)
    workspace = Workspace()
    workspace.select(workspace.active_id)
    app.aboutToQuit.connect(workspace.shutdown)
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
