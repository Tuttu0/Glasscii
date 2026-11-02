import json
import uuid
from pathlib import Path
from PySide6.QtCore import QObject,QSettings,QSignalBlocker
from PySide6.QtWidgets import QApplication,QSystemTrayIcon,QMenu,QInputDialog
from PySide6.QtGui import QColor,QImage,QPixmap,QIcon


class Workspace(QObject):
    def __init__(self,restore=True,tray=True):
        super().__init__()
        self.sessions = {}
        self.active_id = None
        self.stopped = False
        self.settings = QSettings('Glasscii','Desktop')
        self.tray = None
        ids = []
        if restore:
            try:
                ids = json.loads(self.settings.value('session_ids','[]'))
                if not isinstance(ids,list): ids=[]
            except (ValueError,TypeError): ids=[]
        ids = list(dict.fromkeys(key for key in ids if isinstance(key,str) and key.isalnum()))
        if ids:
            for key in ids:
                kind=self.settings.value(f'profiles/{key}/widget_type','image')
                self.add_widget(key,reveal=False,autoload=True,kind=kind)
        else:
            # Migrate the previous single-widget profile, preserving the user's choices.
            key = uuid.uuid4().hex
            if restore:
                for field in ('last_file','cell_size','characters','brightness','highlights','black_point','invert','tint','paper','mode','color','widget_geometry'):
                    value=self.settings.value(field)
                    if value is not None: self.settings.setValue(f'profiles/{key}/{field}',value)
            self.add_widget(key,reveal=False,autoload=restore)
        selected=self.settings.value('active_session') if restore else None
        self.active_id=selected if selected in self.sessions else next(iter(self.sessions))
        self.refresh_pickers()
        if tray and QSystemTrayIcon.isSystemTrayAvailable():
            image=QImage(32,32,QImage.Format.Format_ARGB32)
            image.fill(QColor('#ffffff'))
            self.tray = QSystemTrayIcon(QApplication.windowIcon(), self)
            menu=QMenu()
            menu.addAction('Settings',lambda:self.select(self.active_id))
            widgets_menu=menu.addMenu('Widgets')
            def update_widgets_menu():
                widgets_menu.clear()
                for index,(key,c) in enumerate(self.sessions.items(),1):
                    name=c.display_name or ('Clock' if c.kind=='clock' else (Path(c.committed_path).name if c.committed_path else 'Image'))
                    widgets_menu.addAction(f'{index} · {name}',lambda checked=False, widget_key=key:self.select(widget_key))
            widgets_menu.aboutToShow.connect(update_widgets_menu)
            menu.addAction('Add image widget',lambda:self.add_widget())
            menu.addAction('Add clock date',lambda:self.add_widget(kind='clock'))
            menu.addAction('Quit',self.quit_all)
            self.tray.setContextMenu(menu)
            self.tray_menu=menu
            self.tray.setToolTip('Glasscii · independent desktop widgets')
            self.tray.show()

    def add_widget(self,key=None,reveal=True,autoload=False,kind='image'):
        if self.stopped:return None
        if kind=='clock':
            from clock_widget import ClockController as Controller
        else:
            from app import Controller
        key=key or uuid.uuid4().hex
        controller=Controller(manager=self,session_id=key,autoload=autoload)
        self.sessions[key]=controller
        # Offset newly placed windows instead of stacking them exactly.
        if not controller.settings.contains('widget_geometry'):
            offset=(len(self.sessions)-1)*28
            controller.widget.move(100+offset,100+offset)
        self.active_id=key
        self.refresh_pickers()
        if reveal:self.select(key)
        return controller

    def bind_controls(self,controller):
        controller.widget_picker.currentIndexChanged.connect(
            lambda index:self.select(controller.widget_picker.itemData(index)))
        menu=QMenu(controller.add_widget_button)
        menu.addAction('Image / GIF',lambda:self.add_widget(kind='image'))
        menu.addAction('Clock',lambda:self.add_widget(kind='clock'))
        controller.add_widget_button.setMenu(menu)
        controller.add_widget_button.setToolTip('Add an image widget or a live clock widget')
        controller.remove_widget_button.clicked.connect(lambda:self.remove_widget(controller.session_id))
        controller.rename_widget_button.clicked.connect(lambda:self.rename_widget(controller.session_id))

    def refresh_pickers(self):
        for key,c in self.sessions.items():
            with QSignalBlocker(c.widget_picker):
                c.widget_picker.clear()
                for number,(other_id,other) in enumerate(self.sessions.items(),1):
                    name='Clock' if getattr(other,'kind','image')=='clock' else (Path(other.committed_path).name if other.committed_path else 'Choose image')
                    name=other.display_name or name
                    c.widget_picker.addItem(f'{number} · {name}',other_id)
                c.widget_picker.setCurrentIndex(list(self.sessions).index(key))
            c.remove_widget_button.setEnabled(True)
            c.widget.title.setText(c.display_name or ('CLOCK' if c.kind=='clock' else 'Glasscii'))

    def rename_widget(self,key,name=None):
        if key not in self.sessions:return False
        controller=self.sessions[key]
        if name is None:
            name,ok=QInputDialog.getText(controller,'Rename widget','Widget name (empty = automatic):',text=controller.display_name)
            if not ok:return False
        controller.display_name=str(name).strip()[:48]
        controller.settings.setValue('widget_name',controller.display_name)
        controller.settings.sync();self.refresh_pickers()
        return True

    def select(self,key):
        if key not in self.sessions or self.stopped:return
        self.active_id=key
        for other_id,c in self.sessions.items():
            if other_id!=key:c.hide()
        c=self.sessions[key]
        c.showNormal();c.raise_();c.activateWindow()

    def remove_widget(self,key):
        if key not in self.sessions:return
        c=self.sessions.pop(key)
        c.stop(persist=False)
        c.widget.hide();c.hide()
        c.widget.deleteLater();c.deleteLater()
        self.settings.remove(f'profiles/{key}')
        if not self.sessions:self.add_widget()
        else:
            self.refresh_pickers()
            self.select(next(iter(self.sessions)))
        self.save_index()

    def save_index(self):
        self.settings.setValue('session_ids',json.dumps(list(self.sessions)))
        self.settings.setValue('active_session',self.active_id or '')
        self.settings.sync()

    def shutdown(self):
        if self.stopped:return
        self.stopped=True
        self.save_index()
        for c in self.sessions.values():
            c.persist()  # Record visibility before hiding windows.
            c.stop(persist=False)
            c.widget.hide();c.hide()
        if self.tray:self.tray.hide()

    def quit_all(self):
        self.shutdown()
        QApplication.instance().quit()
