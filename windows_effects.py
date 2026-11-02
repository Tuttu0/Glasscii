import sys
import ctypes
from ctypes import wintypes


def apply_glass(window_id, frosted=False):
    if not frosted:
        # Clear layered transparency: do not place an opaque DWM material beneath it.
        if sys.platform == 'win32':
            try:
                dwm = ctypes.WinDLL('dwmapi')
                dwm.DwmSetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
                dwm.DwmSetWindowAttribute.restype = ctypes.c_long
                none = ctypes.c_int(1)  # DWMSBT_NONE
                dwm.DwmSetWindowAttribute(window_id, 38, ctypes.byref(none), ctypes.sizeof(none))
                class Margins(ctypes.Structure):
                    _fields_ = [(x, ctypes.c_int) for x in ('left', 'right', 'top', 'bottom')]
                dwm.DwmExtendFrameIntoClientArea.argtypes = [wintypes.HWND, ctypes.POINTER(Margins)]
                dwm.DwmExtendFrameIntoClientArea(window_id, ctypes.byref(Margins(0, 0, 0, 0)))
            except (OSError, AttributeError):
                pass
        return 'Clear glass · desktop visible through transparent areas'
    if sys.platform != 'win32':
        return 'Translucent fallback (Windows Acrylic unavailable on this OS)'
    if sys.getwindowsversion().build < 22621:
        return 'Translucent fallback (Acrylic requires Windows 11 build 22621+)'
    try:
        dwm = ctypes.WinDLL('dwmapi')
        dwm.DwmSetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD,
                                            ctypes.c_void_p, wintypes.DWORD]
        dwm.DwmSetWindowAttribute.restype = ctypes.c_long
        class Margins(ctypes.Structure):
            _fields_ = [(x, ctypes.c_int) for x in ('left', 'right', 'top', 'bottom')]
        dwm.DwmExtendFrameIntoClientArea.argtypes = [wintypes.HWND, ctypes.POINTER(Margins)]
        dwm.DwmExtendFrameIntoClientArea.restype = ctypes.c_long
        dwm.DwmExtendFrameIntoClientArea(window_id, ctypes.byref(Margins(-1, -1, -1, -1)))
        rounded = ctypes.c_int(2)
        dwm.DwmSetWindowAttribute(window_id, 33, ctypes.byref(rounded), ctypes.sizeof(rounded))
        acrylic = ctypes.c_int(3)  # DWMSBT_TRANSIENTWINDOW
        result = dwm.DwmSetWindowAttribute(window_id, 38, ctypes.byref(acrylic), ctypes.sizeof(acrylic))
        return 'Windows Acrylic requested' if result == 0 else 'Translucent fallback (DWM declined Acrylic)'
    except (OSError, AttributeError):
        return 'Translucent fallback (DWM unavailable)'
