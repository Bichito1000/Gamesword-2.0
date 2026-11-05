"""Actualizaciones: comprueba un manifiesto JSON alojado por ti y descarga el instalador verificando su SHA-256.

Manifiesto (update.json) — mira tools/make_manifest.py:
  {"version": "1.2.0", "url": "https://tudominio.com/Gamesword-Setup-1.2.0.exe",
   "sha256": "<hash del instalador>", "notes": "Novedades…", "page": "https://tudominio.com/descargas"}
"""
import hashlib
import re
import subprocess
import tempfile
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import requests

from utils.logger import get_logger
from utils.paths import is_frozen

log = get_logger("updater")


class UpdateError(Exception):
    pass


@dataclass
class UpdateInfo:
    version: str
    url: str
    sha256: str
    notes: str = ""
    page: str = ""


def parse_version(v: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", v or "0")[:4]) or (0,)


def _safe_url(url: str) -> bool:
    return url.startswith("https://") or url.startswith("http://127.0.0.1") or url.startswith("http://localhost")


def check(manifest_url: str, current: str) -> Optional[UpdateInfo]:
    """Devuelve la actualización disponible o None. Lanza UpdateError si no se puede comprobar."""
    if not manifest_url:
        raise UpdateError("No hay dirección de actualizaciones configurada (Ajustes → Actualizaciones).")
    if not _safe_url(manifest_url):
        raise UpdateError("La dirección de actualizaciones debe empezar por https://")
    try:
        r = requests.get(manifest_url, timeout=10)
        r.raise_for_status()
        data = r.json()
    except (requests.RequestException, ValueError) as exc:
        raise UpdateError(f"No se pudo comprobar: {exc.__class__.__name__}")
    try:
        info = UpdateInfo(str(data["version"]), str(data.get("url", "")), str(data.get("sha256", "")).lower(),
                          str(data.get("notes", "")), str(data.get("page", "")))
    except KeyError:
        raise UpdateError("El manifiesto de actualización no es válido.")
    return info if parse_version(info.version) > parse_version(current) else None


def download(info: UpdateInfo, progress: Optional[Callable[[int], None]] = None) -> Path:
    """Descarga el instalador y comprueba su hash. Nunca ejecuta nada sin hash válido."""
    if not _safe_url(info.url):
        raise UpdateError("La URL del instalador no es segura (debe ser https).")
    if not re.fullmatch(r"[0-9a-f]{64}", info.sha256):
        raise UpdateError("El manifiesto no incluye un SHA-256 válido; no se instalará por seguridad.")
    dest = Path(tempfile.mkdtemp(prefix="gamesword-update-")) / Path(info.url.split("?")[0]).name
    h = hashlib.sha256()
    try:
        with requests.get(info.url, stream=True, timeout=30) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0))
            done = 0
            with open(dest, "wb") as f:
                for chunk in r.iter_content(1 << 16):
                    f.write(chunk)
                    h.update(chunk)
                    done += len(chunk)
                    if progress and total:
                        progress(int(done * 100 / total))
    except requests.RequestException as exc:
        raise UpdateError(f"Fallo de descarga: {exc.__class__.__name__}")
    if h.hexdigest() != info.sha256:
        dest.unlink(missing_ok=True)
        raise UpdateError("El archivo descargado no coincide con el SHA-256 esperado. Descarga cancelada.")
    return dest


def install(path: Path) -> None:
    """Lanza el instalador (Inno Setup) cerrando y reabriendo Gamesword."""
    subprocess.Popen([str(path), "/SILENT", "/CLOSEAPPLICATIONS", "/RESTARTAPPLICATIONS"])


def can_self_install() -> bool:
    return is_frozen()


def open_page(info: UpdateInfo) -> None:
    webbrowser.open(info.page or info.url)
