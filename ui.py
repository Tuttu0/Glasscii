from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget, QLabel, QPushButton, QComboBox, QSlider, QCheckBox, QLineEdit,
    QVBoxLayout, QHBoxLayout, QGridLayout, QStyle, QScrollArea, QFrame,
)
from renderer import DEFAULT_CHARACTERS
from interaction import ArtCanvas
from ui_motion import AnimatedComboBox as QComboBox, MouseSurface, install_surface_motion
from presets import PresetBar

THEME = """
QMainWindow, QWidget#studioSurface {background:#000000;}
QWidget {font-family:"monospace UI";font-size:12px;color:#f5f5f5;}
QLabel#brand {font-size:30px;font-weight:700;color:#ffffff;}
QLabel#subtitle, QLabel#fileName, QLabel#hint {color:#a0a0a0;font-size:10px;}
QLabel#status {color:#b0b0b0;font-size:10px;}
QLabel#value {color:#000;background:#fff;border-radius:7px;padding:3px 7px;font-size:11px;font-weight:600;}
QPushButton {background:#FFFFFF;color:#000;border:1px solid #fff;border-radius:10px;padding:8px 12px;font-weight:400;}
QPushButton:hover {background:#dedede;border-color:#dedede;}
QPushButton:pressed {background:#bcbcbc;border-color:#bcbcbc;}
QPushButton:disabled {background:#333;color:#888;border-color:#333;}
QPushButton#primary {background:#fff;color:#000;}
QPushButton#primary:hover {background:#dedede;}
QPushButton#primary:pressed {background:#bcbcbc;}
QPushButton#advancedToggle {background:transparent;border:0;text-align:left;color:#bbb;padding:4px 0;font-size:11px;}
QPushButton#advancedToggle:hover {color:#fff;}
QComboBox, QLineEdit {background:#fff;color:#000;border:1px solid #fff;border-radius:9px;padding:7px 10px;selection-background-color:#777;selection-color:#fff;}
QComboBox:hover, QLineEdit:hover {border-color:#bbb;background:#ededed;}
QComboBox:focus, QLineEdit:focus {border:1px solid #aaa;background:#fff;}
QComboBox:disabled, QLineEdit:disabled {color:#888;background:#333;border-color:#333;}
QComboBox::drop-down {border:0;width:24px;}
QComboBox QAbstractItemView {background:#000;color:#fff;selection-background-color:#252525;selection-color:#fff;outline:0;border:1px solid #aaa;padding:4px;}
QSlider {min-height:20px;}
QSlider::groove:horizontal {height:5px;background:#333;border-radius:2px;}
QSlider::sub-page:horizontal {background:#fff;border-radius:2px;}
QSlider::handle:horizontal {width:14px;margin:-5px 0;border-radius:7px;background:#fff;border:2px solid #999;}
QSlider::handle:horizontal:hover {background:#ddd;border-color:#fff;}
QSlider::handle:horizontal:pressed {background:#aaa;}
QSlider::handle:horizontal:disabled {background:#555;}
QCheckBox {spacing:6px;font-size:11px;}
QCheckBox::indicator {width:14px;height:14px;border:1px solid ##ffffff;border-radius:4px;background:#222;}
QCheckBox::indicator:hover {border-color:#fff;background:#444;}
QCheckBox::indicator:checked {background:#fff;border:3px solid ##ffffff;}
QToolTip, QMenu {background:#000;color:#fff;border:1px solid #888;padding:6px;}
QMenu::item:selected {background:#252525;color:#fff;}
QInputDialog {background:#000;color:#fff;}
QScrollArea {background:#000;border:0;}
QScrollBar:vertical {background:#111;width:8px;margin:0;}
QScrollBar::handle:vertical {background:#777;min-height:25px;border-radius:4px;}
QScrollBar::handle:vertical:hover {background:#fff;}
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical {height:0;}
QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical {background:#111;}
"""


class ClickSlider(QSlider):
    """Click anywhere on the bar, drag, wheel, or use the keyboard."""
    def __init__(self, minimum, maximum, value):
        super().__init__(Qt.Orientation.Horizontal)
        self.setRange(minimum, maximum)
        self.setValue(value)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def jump(self, event):
        position = max(0, min(self.width() - 16, round(event.position().x() - 8)))
        self.setValue(QStyle.sliderValueFromPosition(self.minimum(), self.maximum(), position,
                                                     max(1, self.width() - 16), self.invertedAppearance()))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setFocus()
            self.setSliderDown(True)
            self.jump(event)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.isSliderDown() and event.buttons() & Qt.MouseButton.LeftButton:
            self.jump(event)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setSliderDown(False)
            event.accept()
        else:
            super().mouseReleaseEvent(event)




def build_ui(c):
    c.setWindowTitle('Glasscii')
    c.resize(340, 900)
    c.setMinimumWidth(420)
    root = MouseSurface()
    root.setObjectName('studioSurface')
    scroll=QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setWidget(root)
    shell=MouseSurface();shell.setObjectName('studioSurface')
    shell_layout=QVBoxLayout(shell);shell_layout.setContentsMargins(0,0,0,0);shell_layout.setSpacing(0)
    shell_layout.addWidget(scroll,1)
    c.setCentralWidget(shell)
    layout = QVBoxLayout(root)
    c.content_layout=layout
    layout.setContentsMargins(22, 18, 22, 16)
    layout.setSpacing(9)
    header = QHBoxLayout()
    brand = QLabel('Glasscii')
    brand.setObjectName('brand')
    header.addWidget(brand)
    header.addStretch()
    badge = QLabel('DESKTOP WIDGETS')
    badge.setObjectName('value')
    badge.setStyleSheet('font-size:9px;letter-spacing:1px;padding:6px 8px;')
    header.addWidget(badge)
    layout.addLayout(header)
    subtitle = QLabel('A little image. A different desktop.')
    subtitle.setObjectName('subtitle')
    layout.addWidget(subtitle)
    sessions = QHBoxLayout()
    c.widget_picker = QComboBox()
    c.widget_picker.setToolTip('Choose which independent widget to edit')
    sessions.addWidget(c.widget_picker,1)
    c.add_widget_button = QPushButton('+ Add widget')
    c.rename_widget_button=QPushButton('...')
    c.rename_widget_button.setFixedWidth(48)
    c.rename_widget_button.setToolTip('Rename widget')
    sessions.addWidget(c.rename_widget_button)
    c.remove_widget_button = QPushButton('−')
    c.remove_widget_button.setFixedWidth(32)
    c.remove_widget_button.setToolTip('Remove this widget')
    sessions.addWidget(c.add_widget_button)
    sessions.addWidget(c.remove_widget_button)
    layout.addLayout(sessions)
    row = QHBoxLayout()
    c.open_button = QPushButton('Open image / GIF')
    c.open_button.setObjectName('primary')
    c.open_button.clicked.connect(c.choose)
    row.addWidget(c.open_button)
    c.file_label = QLabel('or drop a file')
    c.file_label.setObjectName('fileName')
    c.file_label.setMaximumWidth(185)
    row.addWidget(c.file_label, 1)
    layout.addLayout(row)
    c.preview = ArtCanvas(interactive=True)
    c.preview.setFixedHeight(150)
    layout.addWidget(c.preview, 1)
    c.mode, c.color = QComboBox(), QComboBox()
    c.mode.addItems(['ASCII', 'Halftone', 'Diamonds', 'Voxels'])
    c.color.addItems(['Gray', 'Original colors'])
    c.color.setCurrentIndex(1)
    controls = QGridLayout()
    controls.setHorizontalSpacing(12)
    controls.addWidget(QLabel('Style'), 0, 0)
    controls.addWidget(QLabel('Colors'), 0, 1)
    controls.addWidget(c.mode, 1, 0)
    controls.addWidget(c.color, 1, 1)
    layout.addLayout(controls)
    c.characters = QLineEdit(str(c.settings.value('characters', DEFAULT_CHARACTERS)))
    c.characters.setMaxLength(128)
    c.characters.setPlaceholderText(DEFAULT_CHARACTERS)
    c.characters.setToolTip('Type any printable symbols. Their visual density is measured automatically. Empty = default. Up to 128 characters.')
    c.characters.setFont(QFont('Consolas', 11))
    char_row = QHBoxLayout()
    char_row.addWidget(QLabel('ASCII characters'))
    char_row.addWidget(c.characters, 1)
    c.reset_characters = QPushButton('↺')
    c.reset_characters.setFixedWidth(34)
    c.reset_characters.setToolTip('Reset characters')
    c.reset_characters.clicked.connect(lambda: c.characters.setText(DEFAULT_CHARACTERS))
    char_row.addWidget(c.reset_characters)
    layout.addLayout(char_row)
    def slider_row(label, slider, suffix):
        row = QHBoxLayout()
        title = QLabel(label)
        title.setFixedWidth(72)
        row.addWidget(title)
        row.addWidget(slider, 1)
        value = QLabel()
        value.setObjectName('value')
        value.setMinimumWidth(46)
        value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        slider.valueChanged.connect(lambda x: value.setText(str(x) + suffix))
        value.setText(str(slider.value()) + suffix)
        row.addWidget(value)
        layout.addLayout(row)
        return value
    c.cell_size = ClickSlider(2, 24, int(c.settings.value('cell_size', 4)))
    c.cell_size.setToolTip('Cell width on the desktop widget in logical pixels. Smaller = finer detail; larger = bigger letters or dots. Safe limits are automatic.')
    c.cell_label = slider_row('Cell size', c.cell_size, ' px')
    c.brightness = ClickSlider(30, 200, int(c.settings.value('brightness',100)))
    slider_row('Brightness', c.brightness, '%')
    c.highlights=ClickSlider(-100,100,int(c.settings.value('highlights',0)))
    c.highlights.setToolTip('Adjust bright tones: negative darkens them, positive lifts them. Zero leaves highlights unchanged.')
    slider_row('Highlights',c.highlights,'%')
    c.black_point=ClickSlider(0,80,int(c.settings.value('black_point',0)))
    c.black_point.setToolTip('Raise the black threshold for deeper shadows. Zero keeps the original black point.')
    slider_row('Black point',c.black_point,'%')
    c.reset_adjustments_button=QPushButton('Reset adjustments')
    c.reset_adjustments_button.setToolTip('Restore brightness 100%, highlights 0%, black point 0%, and normal mapping.')
    c.reset_adjustments_button.clicked.connect(c.reset_adjustments)
    layout.addWidget(c.reset_adjustments_button)
    c.speed = ClickSlider(25, 200, 100)
    slider_row('GIF speed', c.speed, '%')
    toggle = QPushButton('▸  Glass & behavior')
    toggle.setObjectName('advancedToggle')
    toggle.setCheckable(True)
    layout.addWidget(toggle)
    advanced = QWidget()
    advanced_layout = QVBoxLayout(advanced)
    advanced_layout.setContentsMargins(0, 0, 0, 0)
    c.paper = QComboBox()
    c.paper.addItems(['Transparent', 'Black', 'White'])
    c.paper.setToolTip('Transparent reveals the desktop. Black / White fill the art background.')
    bg = QHBoxLayout()
    bg.addWidget(QLabel('Background'))
    bg.addWidget(c.paper, 1)
    advanced_layout.addLayout(bg)
    tint_row = QHBoxLayout()
    tint_row.addWidget(QLabel('Glass tint'))
    c.tint = ClickSlider(0, 30, int(c.settings.value('tint', 12)))
    tint_row.addWidget(c.tint, 1)
    advanced_layout.addLayout(tint_row)
    c.invert = QCheckBox('Invert brightness mapping')
    c.invert.setChecked(str(c.settings.value('invert', 'false')).lower() in ('true','1'))
    advanced_layout.addWidget(c.invert)
    c.hide_frame=QCheckBox('Hide widget frame & buttons')
    c.hide_frame.setToolTip('Show only the artwork. Right-click the widget or use tray Settings to restore controls.')
    c.hide_frame.setChecked(str(c.settings.value('hide_frame','false')).lower() in ('true','1'))
    advanced_layout.addWidget(c.hide_frame)
    c.frosted = QCheckBox('Frosted blur')
    c.top = QCheckBox('Always on top')
    c.lock = QCheckBox('Lock widget')
    flags = QHBoxLayout()
    for item in (c.frosted, c.top, c.lock): flags.addWidget(item)
    advanced_layout.addLayout(flags)
    c.effect_label = QLabel('Clear glass · Transparent background reveals the desktop')
    c.effect_label.setObjectName('hint')
    c.effect_label.setWordWrap(True)
    advanced_layout.addWidget(c.effect_label)
    advanced.hide()
    toggle.toggled.connect(advanced.setVisible)
    toggle.toggled.connect(lambda checked: toggle.setText(('▾' if checked else '▸') + '  Glass & behavior'))
    layout.addWidget(advanced)
    c.footer=MouseSurface();c.footer.setObjectName('studioSurface')
    footer_layout=QVBoxLayout(c.footer);footer_layout.setContentsMargins(22,8,22,12);footer_layout.setSpacing(6)
    shell_layout.addWidget(c.footer)
    c.show_button = QPushButton('Place on desktop  ↗')
    c.show_button.setObjectName('primary')
    c.show_button.setCursor(Qt.CursorShape.PointingHandCursor)
    footer_layout.addWidget(c.show_button)
    c.status = QLabel('Ready when you are.')
    c.status.setObjectName('status')
    c.status.setWordWrap(True)
    c.status.setMaximumHeight(32)
    footer_layout.addWidget(c.status)
    for key, control in [('mode', c.mode), ('color', c.color), ('paper', c.paper)]:
        value = c.settings.value(key)
        if value in [control.itemText(i) for i in range(control.count())]: control.setCurrentText(value)
    for button in root.findChildren(QPushButton): button.setCursor(Qt.CursorShape.PointingHandCursor)
    for combo in root.findChildren(QComboBox): combo.setCursor(Qt.CursorShape.PointingHandCursor)

    c.presets=PresetBar(c)
    layout.insertWidget(layout.indexOf(c.preview)+2,c.presets)
    install_surface_motion(c,[root,shell,c.footer])
