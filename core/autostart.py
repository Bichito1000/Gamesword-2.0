"""Inicio automático con Windows (clave Run del usuario, sin permisos de administrador)."""
import sys
from pathlib import Path

from utils.paths import app_dir, is_frozen

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE = "Gamesword"

try:
    import winreg
except ImportError:
    winreg = None


def command() -> str:
    if is_frozen():
        return f'"{sys.executable}" --minimized'
    exe = Path(sys.executable)
    pyw = exe.with_name("pythonw.exe")
    return f'"{pyw if pyw.exists() else exe}" "{app_dir() / "main.py"}" --minimized'


def is_enabled() -> bool:
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            return bool(winreg.QueryValueEx(k, VALUE)[0])
    except OSError:
        return False


def set_enabled(enabled: bool) -> bool:
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            if enabled:
                winreg.SetValueEx(k, VALUE, 0, winreg.REG_SZ, command())
            else:
                try:
                    winreg.DeleteValue(k, VALUE)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        return False
