import json
from PySide6.QtCore import QObject,QSettings,Signal,QSignalBlocker
from PySide6.QtGui import QColor,QFont
from PySide6.QtWidgets import QWidget,QHBoxLayout,QPushButton,QInputDialog,QApplication
from ui_motion import AnimatedComboBox

IMAGE_FIELDS={'mode':'mode','color':'color','paper':'paper','cell_size':'cell_size',
              'characters':'characters','brightness':'brightness','highlights':'highlights',
              'black_point':'black_point','invert':'invert','tint':'tint','speed':'speed'}
CLOCK_FIELDS={'time_format':'time_format','date_format':'date_format','alignment':'alignment',
              'seconds':'seconds','show_date':'show_date','bold':'bold','font_size':'font_size',
              'date_size':'date_size','caption':'caption','paper':'paper','tint':'tint'}


def capture_preset(controller):
    fields=CLOCK_FIELDS if controller.kind=='clock' else IMAGE_FIELDS
    result={}
    for key,attribute in fields.items():
        control=getattr(controller,attribute)
        if hasattr(control,'isChecked'):result[key]=control.isChecked()
        elif hasattr(control,'currentText'):result[key]=control.currentText()
        elif hasattr(control,'value'):result[key]=control.value()
        else:result[key]=control.text()
    if controller.kind=='clock':
        result.update(font=controller.fonts.currentFont().family(),
                      time_color=controller.time_color.name(),date_color=controller.date_color.name())
    return result


def apply_preset(controller,values):
    if getattr(controller,'loader',None) is not None:
        controller.status.setText('Wait for loading to finish before applying a preset.')
        return False
    fields=CLOCK_FIELDS if controller.kind=='clock' else IMAGE_FIELDS
    # Let valueChanged update value labels; suppress only expensive conversion/render slots.
    controller.applying_preset=True
    try:
        if controller.kind=='image':
            controller.debounce.stop();controller.style_debounce.stop()
            controller.cell_size.setMinimum(2)
        for key,attribute in fields.items():
            if key not in values:continue
            control=getattr(controller,attribute);value=values[key]
            if hasattr(control,'isChecked'):
                if isinstance(value,bool):control.setChecked(value)
            elif hasattr(control,'currentText'):
                if isinstance(value,str) and control.findText(value)>=0:control.setCurrentText(value)
            elif hasattr(control,'value'):
                if isinstance(value,int):control.setValue(value)
            elif isinstance(value,str):control.setText(value)
        if controller.kind=='clock':
            if isinstance(values.get('font'),str):controller.fonts.setCurrentFont(QFont(values['font']))
            for key in ('time_color','date_color'):
                if isinstance(values.get(key),str):
                    color=QColor(values[key])
                    if color.isValid():setattr(controller,key,color)
            controller.update_color_labels()
    finally:
        controller.applying_preset=False
    if controller.kind=='image':
        controller.debounce.stop();controller.style_debounce.stop()
        if controller.path:controller.reload()
        else:controller.queue_reload()
        controller.change_tint(controller.tint.value())
    else:
        controller.change_tint(controller.tint.value());controller.render_clock()
    return True


class PresetStore(QObject):
    changed=Signal(str)
    def __init__(self,parent=None):
        super().__init__(parent)
        self.settings=QSettings('Glassci','Presets')

    def read(self,kind):
        try:
            value=json.loads(self.settings.value(kind,'{}'))
            return {name:payload for name,payload in value.items() if isinstance(name,str) and isinstance(payload,dict)} if isinstance(value,dict) else {}
        except (ValueError,TypeError):return {}

    def save(self,kind,name,values):
        name=name.strip()[:64]
        if not name:return False
        items=self.read(kind);items[name]=values
        self.settings.setValue(kind,json.dumps(items,ensure_ascii=False));self.settings.sync()
        self.changed.emit(kind);return True

    def remove(self,kind,name):
        items=self.read(kind)
        if name not in items:return
        del items[name]
        self.settings.setValue(kind,json.dumps(items,ensure_ascii=False));self.settings.sync()
        self.changed.emit(kind)


_store=None

def preset_store():
    global _store
    if _store is None:_store=PresetStore(QApplication.instance())
    return _store


class PresetBar(QWidget):
    def __init__(self,controller):
        super().__init__()
        self.controller=controller;self.store=preset_store()
        row=QHBoxLayout(self);row.setContentsMargins(0,0,0,0);row.setSpacing(7)
        self.picker=AnimatedComboBox();self.picker.setToolTip('Choose a saved visual preset. Image paths and widget positions stay unchanged.')
        row.addWidget(self.picker,1)
        self.save_button=QPushButton('Save');self.delete_button=QPushButton('×')
        self.delete_button.setFixedWidth(32);self.delete_button.setToolTip('Delete selected preset')
        row.addWidget(self.save_button);row.addWidget(self.delete_button)
        self.save_button.clicked.connect(self.save_dialog);self.delete_button.clicked.connect(self.delete_selected)
        self.picker.activated.connect(self.apply_selected)
        self.store.changed.connect(self.on_store_changed)
        self.refresh()

    def on_store_changed(self,kind):
        if kind==self.controller.kind:self.refresh()

    def refresh(self):
        selected=self.picker.currentData()
        with QSignalBlocker(self.picker):
            self.picker.clear();self.picker.addItem('Presets…',None)
            for name in sorted(self.store.read(self.controller.kind),key=str.casefold):self.picker.addItem(name,name)
            index=self.picker.findData(selected)
            self.picker.setCurrentIndex(max(0,index))
        self.delete_button.setEnabled(self.picker.currentData() is not None)

    def save_dialog(self):
        name,ok=QInputDialog.getText(self,'Save preset','Preset name:',text=self.picker.currentData() or '')
        if ok and self.store.save(self.controller.kind,name,capture_preset(self.controller)):
            self.picker.setCurrentIndex(self.picker.findData(name.strip()[:64]))
            self.delete_button.setEnabled(True)
            self.controller.status.setText('Preset saved: '+name.strip()[:64])

    def apply_selected(self,*_):
        name=self.picker.currentData();self.delete_button.setEnabled(name is not None)
        if name is None:return
        payload=self.store.read(self.controller.kind).get(name)
        if payload is not None and apply_preset(self.controller,payload):self.controller.status.setText('Preset applied: '+name)

    def delete_selected(self):
        name=self.picker.currentData()
        if name is not None:self.store.remove(self.controller.kind,name)
