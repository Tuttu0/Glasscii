from datetime import datetime
from PySide6.QtCore import Qt,QTimer,QSettings,QRectF
from PySide6.QtGui import QColor,QFont,QFontMetricsF,QImage,QPainter
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,
    QFormLayout,QLabel,QPushButton,QComboBox,QCheckBox,QFontComboBox,QColorDialog,
    QLineEdit,QScrollArea,QFrame)
from ui import ArtCanvas,ClickSlider
from ui_motion import AnimatedComboBox as QComboBox,AnimatedFontComboBox as QFontComboBox,MouseSurface,install_surface_motion
from presets import PresetBar
from app import GlassWidget
from windows_effects import apply_glass

DATE_FORMATS={'Day / Month / Year':'%d / %m / %Y','ISO date':'%Y-%m-%d',
              'Long date':'%A, %d %B %Y'}


def clock_text(now,twenty_four=True,seconds=False,date_format='%d / %m / %Y'):
    pattern='%H:%M' if twenty_four else '%I:%M'
    if seconds:pattern+=':%S'
    if not twenty_four:pattern+=' %p'
    return now.strftime(pattern),now.strftime(date_format)


class ClockController(QMainWindow):
    kind='clock'
    def __init__(self,manager=None,session_id=None,autoload=True,now_provider=None):
        super().__init__()
        self.manager,self.session_id=manager,session_id
        self.settings=QSettings('Glasscii','Desktop')
        self.settings.beginGroup(f'profiles/{session_id}' if manager else 'standalone_clock')
        self.settings.setValue('widget_type','clock')
        self.committed_path=''
        self.display_name=str(self.settings.value('widget_name','')).strip()
        self.applying_preset=False
        self.closing=False
        self.now_provider=now_provider or (lambda:datetime.now().astimezone())
        self.time_color=QColor(self.settings.value('time_color','#ffffff'))
        self.date_color=QColor(self.settings.value('date_color','#b0b0b0'))
        if not self.time_color.isValid():self.time_color=QColor('#ffffff')
        if not self.date_color.isValid():self.date_color=QColor('#b0b0b0')
        self.setWindowTitle('Glasscii · Clock & date')
        self.resize(460,700);self.setMinimumWidth(420)
        root=MouseSurface();root.setObjectName('studioSurface')
        scroll=QScrollArea();scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(root)
        shell=MouseSurface();shell.setObjectName('studioSurface')
        shell_layout=QVBoxLayout(shell);shell_layout.setContentsMargins(0,0,0,0);shell_layout.setSpacing(0)
        shell_layout.addWidget(scroll,1);self.setCentralWidget(shell)
        layout=QVBoxLayout(root);layout.setContentsMargins(22,18,22,16);layout.setSpacing(10)
        title=QLabel('Clock & date');title.setObjectName('brand');layout.addWidget(title)
        subtitle=QLabel('Live local time. Your own desktop clock.')
        subtitle.setObjectName('subtitle');layout.addWidget(subtitle)
        row=QHBoxLayout()
        self.widget_picker=QComboBox();row.addWidget(self.widget_picker,1)
        self.add_widget_button=QPushButton('+ Add widget');row.addWidget(self.add_widget_button)
        self.rename_widget_button=QPushButton('…');self.rename_widget_button.setFixedWidth(32)
        self.rename_widget_button.setToolTip('Rename widget');row.addWidget(self.rename_widget_button)
        self.remove_widget_button=QPushButton('−');self.remove_widget_button.setFixedWidth(32)
        self.remove_widget_button.setToolTip('Remove this clock');row.addWidget(self.remove_widget_button)
        layout.addLayout(row)
        self.preview=ArtCanvas(interactive=True);self.preview.setFixedHeight(160)
        self.preview.setToolTip('Live clock preview · time comes from your computer')
        layout.addWidget(self.preview)
        form=QFormLayout();form.setSpacing(9)
        self.time_format=QComboBox();self.time_format.addItems(['24-hour','12-hour'])
        self.date_format=QComboBox();self.date_format.addItems(list(DATE_FORMATS))
        self.fonts=QFontComboBox();self.fonts.setEditable(False)
        self.fonts.setCurrentFont(QFont(str(self.settings.value('clock_font','Consolas'))))
        self.alignment=QComboBox();self.alignment.addItems(['Center','Left','Right'])
        for key,control in [('time_format',self.time_format),('date_format',self.date_format),('clock_alignment',self.alignment)]:
            value=self.settings.value(key)
            if value in [control.itemText(i) for i in range(control.count())]:control.setCurrentText(value)
        form.addRow('Time format',self.time_format)
        form.addRow('Date format',self.date_format)
        form.addRow('Font',self.fonts)
        form.addRow('Alignment',self.alignment)
        layout.addLayout(form)
        flags=QHBoxLayout()
        self.seconds=QCheckBox('Seconds');self.show_date=QCheckBox('Show date');self.bold=QCheckBox('Bold')
        for key,control,default in [('seconds',self.seconds,False),('show_date',self.show_date,True),('clock_bold',self.bold,True)]:
            control.setChecked(str(self.settings.value(key,str(default))).lower() in ('true','1'))
            flags.addWidget(control)
        layout.addLayout(flags)
        def bar(label,control):
            row=QHBoxLayout();name=QLabel(label);name.setFixedWidth(72);row.addWidget(name)
            row.addWidget(control,1);value=QLabel(str(control.value())+' px');value.setObjectName('value')
            value.setMinimumWidth(48);row.addWidget(value)
            control.valueChanged.connect(lambda v:value.setText(str(v)+' px'))
            layout.addLayout(row)
        self.font_size=ClickSlider(24,120,int(self.settings.value('font_size',72)))
        self.font_size.setToolTip('Font size in widget pixels; shrinks to fit if the clock is too narrow.')
        self.date_size=ClickSlider(10,42,int(self.settings.value('date_size',20)))
        bar('Time size',self.font_size);bar('Date size',self.date_size)
        colors=QHBoxLayout()
        self.time_color_button=QPushButton();self.date_color_button=QPushButton()
        colors.addWidget(self.time_color_button);colors.addWidget(self.date_color_button)
        layout.addLayout(colors);self.update_color_labels()
        self.time_color_button.clicked.connect(lambda:self.choose_color('time'))
        self.date_color_button.clicked.connect(lambda:self.choose_color('date'))
        self.caption=QLineEdit(str(self.settings.value('clock_caption','')))
        self.caption.setMaxLength(48);self.caption.setPlaceholderText('Optional caption, e.g. Baghdad')
        layout.addWidget(self.caption)
        self.paper=QComboBox();self.paper.addItems(['Transparent','Black','White'])
        paper=self.settings.value('paper','Transparent')
        if paper in ['Transparent','Black','White']:self.paper.setCurrentText(paper)
        background=QHBoxLayout();background.addWidget(QLabel('Background'));background.addWidget(self.paper,1)
        layout.addLayout(background)
        tint=QHBoxLayout();tint.addWidget(QLabel('Glass tint'))
        self.tint=ClickSlider(0,100,int(self.settings.value('tint',12)));tint.addWidget(self.tint,1)
        layout.addLayout(tint)
        controls=QHBoxLayout()
        self.hide_frame=QCheckBox('Hide widget frame & buttons')
        self.hide_frame.setChecked(str(self.settings.value('hide_frame','false')).lower() in ('true','1'))
        layout.addWidget(self.hide_frame)
        self.frosted=QCheckBox('Frosted blur');self.top=QCheckBox('Always on top');self.lock=QCheckBox('Lock widget')
        for c in (self.frosted,self.top,self.lock):controls.addWidget(c)
        layout.addLayout(controls)
        self.effect_label=QLabel('Clear glass · transparent clock background')
        self.effect_label.setObjectName('hint');self.effect_label.setWordWrap(True);layout.addWidget(self.effect_label)
        footer=MouseSurface();footer.setObjectName('studioSurface')
        footer_layout=QVBoxLayout(footer);footer_layout.setContentsMargins(22,8,22,12);footer_layout.setSpacing(6)
        shell_layout.addWidget(footer)
        self.show_button=QPushButton('Place clock on desktop  ↗');self.show_button.setObjectName('primary')
        self.show_button.setCursor(Qt.CursorShape.PointingHandCursor)
        footer_layout.addWidget(self.show_button)
        self.status=QLabel('Uses your computer’s local date, time and time zone.')
        self.status.setObjectName('status');self.status.setWordWrap(True);footer_layout.addWidget(self.status)
        self.widget=GlassWidget(self);self.widget.resize(440,240)
        self.widget.setWindowTitle('Glasscii · Clock & date')
        self.widget.tint=self.tint.value()
        self.widget.set_frame_hidden(self.hide_frame.isChecked())
        self.hide_frame.toggled.connect(self.widget.set_frame_hidden)
        geometry=self.settings.value('widget_geometry')
        if geometry:self.widget.restoreGeometry(geometry)
        self.widget.layout().activate()
        for signal in (self.time_format.currentTextChanged,self.date_format.currentTextChanged,
            self.fonts.currentFontChanged,self.alignment.currentTextChanged,self.seconds.toggled,
            self.show_date.toggled,self.bold.toggled,self.font_size.valueChanged,self.date_size.valueChanged,
            self.caption.textChanged,self.paper.currentTextChanged,self.widget.resized):
            signal.connect(lambda *_:self.render_clock())
        self.show_button.clicked.connect(self.show_widget)
        self.top.toggled.connect(self.change_top);self.lock.toggled.connect(self.change_lock)
        self.tint.valueChanged.connect(self.change_tint);self.frosted.toggled.connect(self.change_glass)
        if manager:manager.bind_controls(self)
        else:
            self.widget_picker.addItem('Clock & date')
            self.add_widget_button.setEnabled(False);self.remove_widget_button.setEnabled(False);self.rename_widget_button.setEnabled(False)
        for button in root.findChildren(QPushButton):button.setCursor(Qt.CursorShape.PointingHandCursor)
        for combo in root.findChildren(QComboBox):combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.presets=PresetBar(self);layout.insertWidget(layout.indexOf(self.preview)+1,self.presets)
        install_surface_motion(self,[root,shell,footer])
        self.fonts.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clock_timer=QTimer(self);self.clock_timer.setInterval(1000)
        self.clock_timer.timeout.connect(self.render_clock);self.clock_timer.start()
        self.render_clock()
        screen=self.screen();limit=screen.availableGeometry().height()-70 if screen else 850
        layout.activate();self.resize(460,min(limit,layout.sizeHint().height()+footer.sizeHint().height()))
        if autoload and str(self.settings.value('widget_visible','false')).lower() in ('true','1'):
            QTimer.singleShot(0,self.show_widget)

    def update_color_labels(self):
        self.time_color_button.setText('Time · '+self.time_color.name())
        self.date_color_button.setText('Date · '+self.date_color.name())

    def choose_color(self,target):
        selected=QColorDialog.getColor(self.time_color if target=='time' else self.date_color,
                                       self,'Choose '+target+' color')
        if selected.isValid():
            if target=='time':self.time_color=selected
            else:self.date_color=selected
            self.update_color_labels();self.render_clock()

    def render_clock(self,now=None):
        if self.closing or self.applying_preset:return
        now=now or self.now_provider()
        self.last_text=clock_text(now,self.time_format.currentText()=='24-hour',self.seconds.isChecked(),
                                  DATE_FORMATS[self.date_format.currentText()])
        width=max(1,self.widget.canvas.width());height=max(1,self.widget.canvas.height())
        image=QImage(width,height,QImage.Format.Format_ARGB32_Premultiplied)
        image.fill({'Transparent':Qt.GlobalColor.transparent,'Black':QColor('#080a0e'),'White':QColor('#fafafa')}[self.paper.currentText()])
        lines=[]
        if self.caption.text().strip():lines.append((self.caption.text().strip(),self.date_size.value(),self.date_color,False))
        lines.append((self.last_text[0],self.font_size.value(),self.time_color,self.bold.isChecked()))
        if self.show_date.isChecked():lines.append((self.last_text[1],self.date_size.value(),self.date_color,False))
        prepared=[]
        for text,size,color,bold in lines:
            font=QFont(self.fonts.currentFont());font.setPixelSize(size);font.setBold(bold)
            metrics=QFontMetricsF(font)
            scale=min(1.,max(1,width-24)/max(1,metrics.horizontalAdvance(text)))
            font.setPixelSize(max(8,round(size*scale)))
            prepared.append((text,font,color))
        total=sum(QFontMetricsF(font).height() for _,font,_ in prepared)+8*(len(prepared)-1)
        if total>height-12:
            scale=max(1,height-12)/total
            for _,font,_ in prepared:font.setPixelSize(max(6,round(font.pixelSize()*scale)))
        total=sum(QFontMetricsF(font).height() for _,font,_ in prepared)+8*(len(prepared)-1)
        y=max(0,(height-total)/2)
        painter=QPainter(image);painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        alignment={'Center':Qt.AlignmentFlag.AlignHCenter,'Left':Qt.AlignmentFlag.AlignLeft,'Right':Qt.AlignmentFlag.AlignRight}[self.alignment.currentText()]
        for text,font,color in prepared:
            painter.setFont(font);painter.setPen(color)
            h=QFontMetricsF(font).height()
            painter.drawText(QRectF(12,y,max(1,width-24),h),alignment|Qt.AlignmentFlag.AlignVCenter,text)
            y+=h+8
        painter.end()
        self.preview.set_art(image,0,0,self.paper.currentText())
        self.widget.canvas.set_art(image,0,0,self.paper.currentText())

    def show_widget(self):
        if self.closing:return
        self.render_clock();self.widget.show();self.widget.raise_()

    def reveal(self):
        if self.manager:self.manager.select(self.session_id)
        else:self.showNormal();self.raise_();self.activateWindow()

    def change_glass(self,*_):
        self.widget.request_effect_update()
        self.widget.update()

    def change_tint(self,value):self.widget.tint=value;self.widget.update()

    def change_top(self,enabled):
        visible=self.widget.isVisible();self.widget.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint,enabled)
        if visible:self.widget.show()

    def change_lock(self,enabled):
        self.widget.locked=enabled;self.widget.grip.setVisible(not enabled and not self.widget.frame_hidden)
        if enabled:self.widget.setFixedSize(self.widget.size())
        else:self.widget.setMinimumSize(220,200);self.widget.setMaximumSize(16777215,16777215)

    def persist(self):
        values={'hide_frame':self.hide_frame.isChecked(),'widget_name':self.display_name,'widget_type':'clock','time_format':self.time_format.currentText(),'date_format':self.date_format.currentText(),
            'clock_font':self.fonts.currentFont().family(),'clock_alignment':self.alignment.currentText(),
            'seconds':self.seconds.isChecked(),'show_date':self.show_date.isChecked(),'clock_bold':self.bold.isChecked(),
            'font_size':self.font_size.value(),'date_size':self.date_size.value(),
            'time_color':self.time_color.name(),'date_color':self.date_color.name(),'clock_caption':self.caption.text(),
            'paper':self.paper.currentText(),'tint':self.tint.value(),'widget_visible':self.widget.isVisible(),
            'widget_geometry':self.widget.saveGeometry()}
        for key,value in values.items():self.settings.setValue(key,value)
        self.settings.sync()

    def stop(self,persist=True):
        if self.closing:return
        if persist:self.persist()
        self.closing=True;self.clock_timer.stop()
        self.widget.stop_updates()
        self.preview.fit_timer.stop()
        self.ui_motion.stop()
        self.preview.effect_timer.stop();self.widget.canvas.effect_timer.stop()

    def closeEvent(self,event):
        self.persist()
        visible=self.widget.isVisible() or (self.manager and any(c.widget.isVisible() for c in self.manager.sessions.values()))
        if visible and not self.closing:self.hide();event.ignore()
        else:
            if self.manager:self.manager.quit_all()
            else:self.stop();QApplication.instance().quit()
            event.accept()
