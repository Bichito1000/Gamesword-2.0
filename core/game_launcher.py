"""Lanzamiento de juegos: ejecutables directos o URIs de las plataformas."""
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from utils.helpers import open_uri
from utils.logger import get_logger
from .models import Game

log = get_logger("launcher")


@dataclass
class LaunchResult:
    ok: bool
    message: str
    pid: Optional[int] = None


def launch_game(game: Game) -> LaunchResult:
    exe = Path(game.exe_path) if game.exe_path else None
    try:
        if exe and exe.exists():
            cwd = game.install_dir if game.install_dir and Path(game.install_dir).is_dir() else str(exe.parent)
            try:
                proc = subprocess.Popen([str(exe)], cwd=cwd)
                return LaunchResult(True, f"Iniciando {game.name}…", proc.pid)
            except OSError as exc:
                # WinError 740: el juego exige permisos de administrador -> ShellExecute pedirá UAC
                if getattr(exc, "winerror", None) == 740 and hasattr(os, "startfile"):
                    os.startfile(str(exe))  # type: ignore[attr-defined]
                    return LaunchResult(True, f"Iniciando {game.name} (permisos de administrador)…")
                raise
        if game.launch_uri:
            open_uri(game.launch_uri)
            return LaunchResult(True, f"Iniciando {game.name} desde {game.platform.title()}…")
    except Exception as exc:  # noqa: BLE001
        log.exception("Error al lanzar %s", game.name)
        return LaunchResult(False, f"No se pudo iniciar {game.name}: {exc}")
    if exe:
        return LaunchResult(False, f"No existe el ejecutable de {game.name}: {exe}")
    return LaunchResult(False, f"{game.name} no tiene ejecutable ni URI configurados. Edítalo en la biblioteca.")
