"""Rutas de la aplicación (modo desarrollo y modo .exe empaquetado)."""
import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_dir() -> Path:
    """Carpeta donde vive el código (o el .exe)."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _user_root() -> Path:
    """Dónde se guardan los datos del usuario.

    - Desarrollo: carpeta del proyecto (portable).
    - Instalado (.exe): %LOCALAPPDATA%\\Gamesword, porque Program Files es de solo lectura.
    """
    if is_frozen():
        base = os.environ.get("LOCALAPPDATA") or str(Path.home())
        return Path(base) / "Gamesword"
    return app_dir()


def _ensure(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


def data_dir() -> Path:
    return _ensure(_user_root() / "data")


def logs_dir() -> Path:
    return _ensure(_user_root() / "logs")


def covers_dir() -> Path:
    return _ensure(data_dir() / "covers")
