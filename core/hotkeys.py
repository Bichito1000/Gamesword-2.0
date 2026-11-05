"""Atajos globales de Windows (funcionan aunque Gamesword no tenga el foco)."""
import sys
import threading
import time

from PySide6.QtCore import QObject, Signal

from utils.logger import get_logger

log = get_logger("hotkeys")

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x4000
WM_HOTKEY, PM_REMOVE = 0x0312, 0x0001

# id -> (nombre de acción, modificadores, tecla virtual)
HOTKEYS = {
    1: ("toggle", MOD_CONTROL | MOD_ALT, 0x47),   # Ctrl+Alt+G  -> mostrar/ocultar Gamesword
    2: ("voice", MOD_CONTROL | MOD_ALT, 0x56),    # Ctrl+Alt+V  -> hablar con Gamesword AI
}
LABELS = {"toggle": "Ctrl+Alt+G", "voice": "Ctrl+Alt+V"}


class HotkeyManager(QObject):
    triggered = Signal(str)

    def __init__(self):
        super().__init__()
        self._stop = threading.Event()
        self._thread = None

    def start(self) -> None:
        if sys.platform != "win32" or (self._thread is not None and self._thread.is_alive()):
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="hotkeys")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        registered = []
        for hid, (name, mod, vk) in HOTKEYS.items():
            if user32.RegisterHotKey(None, hid, mod | MOD_NOREPEAT, vk):
                registered.append(hid)
            else:
                log.warning("No se pudo registrar el atajo %s (¿ya está en uso?)", LABELS[name])
        msg = wintypes.MSG()
        try:
            while not self._stop.is_set():
                if user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
                    if msg.message == WM_HOTKEY and msg.wParam in HOTKEYS:
                        self.triggered.emit(HOTKEYS[msg.wParam][0])
                else:
                    time.sleep(0.05)
        finally:
            for hid in registered:
                user32.UnregisterHotKey(None, hid)
