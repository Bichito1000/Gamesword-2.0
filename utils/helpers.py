"""Funciones auxiliares sin dependencias de Qt."""
import hashlib
import os
import re
import subprocess
import sys
import unicodedata
import webbrowser
from datetime import datetime
from pathlib import Path


def normalize(text: str) -> str:
    """Minúsculas, sin acentos ni signos: 'Ábreme  Fortnite!' -> 'abreme fortnite'."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-zA-Z0-9]+", " ", text.lower())
    return text.strip()


def format_duration(seconds: int) -> str:
    """7380 -> '2h 03m'; 540 -> '9m'; 20 -> '20s'."""
    seconds = int(max(0, seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m:02d}m"
    if m:
        return f"{m}m"
    return f"{s}s"


def format_hours(seconds: int) -> str:
    """Horas con un decimal: 5400 -> '1.5 h'."""
    return f"{seconds / 3600:.1f} h"


def format_clock(seconds: int) -> str:
    seconds = int(max(0, seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def parse_iso(value: str):
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def time_ago(value: str) -> str:
    dt = parse_iso(value)
    if not dt:
        return "nunca"
    delta = datetime.now() - dt
    secs = int(delta.total_seconds())
    if secs < 60:
        return "hace un momento"
    if secs < 3600:
        return f"hace {secs // 60} min"
    if secs < 86400:
        return f"hace {secs // 3600} h"
    days = secs // 86400
    if days == 1:
        return "ayer"
    if days < 30:
        return f"hace {days} días"
    return dt.strftime("%d/%m/%Y")


def color_from_text(text: str) -> tuple:
    """Color HSV estable a partir de un texto (para portadas sin imagen)."""
    h = int(hashlib.md5((text or "").encode("utf-8")).hexdigest()[:6], 16)
    return h % 360, 150 + (h >> 8) % 80, 110 + (h >> 16) % 60


def open_uri(uri: str) -> None:
    """Abre un URI (steam://, https://...) con la aplicación asociada."""
    if sys.platform == "win32":
        os.startfile(uri)  # type: ignore[attr-defined]
    else:
        webbrowser.open(uri)


def open_in_explorer(path) -> None:
    p = Path(path)
    target = p if p.is_dir() else p.parent
    if not target.exists():
        return
    if sys.platform == "win32":
        os.startfile(str(target))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(target)])
    else:
        subprocess.Popen(["xdg-open", str(target)])


def greeting() -> str:
    h = datetime.now().hour
    if h < 6:
        return "Buenas noches"
    if h < 13:
        return "Buenos días"
    if h < 21:
        return "Buenas tardes"
    return "Buenas noches"
