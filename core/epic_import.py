"""Biblioteca completa de Epic Games mediante la herramienta de código abierto «legendary» (opcional).

Epic no ofrece una API oficial para listar tu biblioteca. «legendary» (pip install legendary-gl) inicia sesión
con la web oficial de Epic: Gamesword nunca ve tu contraseña. Primera vez:  legendary auth
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List

from utils.logger import get_logger
from .models import DetectedGame

log = get_logger("epic")
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class EpicImportError(Exception):
    pass


def legendary_command() -> List[str]:
    exe = shutil.which("legendary")
    if exe:
        return [exe]
    local = Path(sys.executable).with_name("Scripts") / "legendary.exe"
    if local.exists():
        return [str(local)]
    try:
        import legendary  # noqa: F401
        return [sys.executable, "-m", "legendary"]
    except ImportError:
        return []


def read_owned() -> List[DetectedGame]:
    cmd = legendary_command()
    if not cmd:
        raise EpicImportError("Para ver tu biblioteca completa de Epic instala «legendary»: pip install legendary-gl "
                              "y ejecuta  legendary auth  una vez.")
    try:
        r = subprocess.run(cmd + ["list", "--json"], capture_output=True, text=True, timeout=90,
                           creationflags=_NO_WINDOW)
    except (OSError, subprocess.SubprocessError) as exc:
        raise EpicImportError(f"No se pudo ejecutar legendary: {exc}")
    try:
        data = json.loads(r.stdout)
    except ValueError:
        raise EpicImportError("legendary no devolvió la biblioteca. ¿Has iniciado sesión? Ejecuta:  legendary auth")
    out = []
    for item in data if isinstance(data, list) else []:
        app, title = item.get("app_name"), item.get("app_title") or (item.get("metadata") or {}).get("title")
        if app and title:
            out.append(DetectedGame(name=title, platform="epic", external_id=app,
                                    launch_uri=f"com.epicgames.launcher://apps/{app}?action=install",
                                    installed=False))
    return out
