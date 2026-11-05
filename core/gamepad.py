"""Navegación con mando (XInput de Windows: Xbox y compatibles). Solo actúa si Gamesword tiene el foco."""
import sys
import time

from PySide6.QtCore import QObject, QTimer, Signal

from utils.logger import get_logger

log = get_logger("gamepad")

BUTTONS = {0x1: "up", 0x2: "down", 0x4: "left", 0x8: "right", 0x1000: "accept", 0x2000: "back",
           0x4000: "tab", 0x8000: "backtab", 0x100: "prev", 0x200: "next", 0x10: "menu"}
REPEATABLE = {"up", "down", "left", "right"}
DEADZONE = 16000


def _load_xinput():
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    class Gamepad(ctypes.Structure):
        _fields_ = [("wButtons", wintypes.WORD), ("bLeftTrigger", ctypes.c_ubyte),
                    ("bRightTrigger", ctypes.c_ubyte), ("sThumbLX", ctypes.c_short), ("sThumbLY", ctypes.c_short),
                    ("sThumbRX", ctypes.c_short), ("sThumbRY", ctypes.c_short)]

    class State(ctypes.Structure):
        _fields_ = [("dwPacketNumber", wintypes.DWORD), ("Gamepad", Gamepad)]

    for name in ("xinput1_4", "xinput1_3", "xinput9_1_0"):
        try:
            dll = getattr(ctypes.windll, name)
            return dll.XInputGetState, State, ctypes
        except (OSError, AttributeError):
            continue
    return None


class GamepadPoller(QObject):
    action = Signal(str)

    def __init__(self):
        super().__init__()
        self._x = _load_xinput()
        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._poll)
        self._held = {}            # acción -> (instante de pulsación, última repetición)
        self._connected = None
        self._next_scan = 0.0

    @property
    def available(self) -> bool:
        return self._x is not None

    def start(self) -> None:
        if self._x:
            self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def _read(self):
        get_state, State, ctypes = self._x
        now = time.monotonic()
        indexes = [self._connected] if self._connected is not None else (range(4) if now >= self._next_scan else [])
        for i in indexes:
            st = State()
            if get_state(i, ctypes.byref(st)) == 0:
                self._connected = i
                return st.Gamepad
            self._connected = None
        if self._connected is None:
            self._next_scan = now + 2.0      # sin mando: buscar solo cada 2 s
        return None

    def _poll(self) -> None:
        pad = self._read()
        now = time.monotonic()
        if pad is None:
            self._held.clear()
            return
        active = {name for bit, name in BUTTONS.items() if pad.wButtons & bit}
        if pad.sThumbLX > DEADZONE:
            active.add("right")
        elif pad.sThumbLX < -DEADZONE:
            active.add("left")
        if pad.sThumbLY > DEADZONE:
            active.add("up")
        elif pad.sThumbLY < -DEADZONE:
            active.add("down")
        for name in list(self._held):
            if name not in active:
                del self._held[name]
        for name in active:
            if name not in self._held:
                self._held[name] = (now, now)
                self.action.emit(name)
            elif name in REPEATABLE:
                since, last = self._held[name]
                if now - since > 0.4 and now - last > 0.12:
                    self._held[name] = (since, now)
                    self.action.emit(name)
