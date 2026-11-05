"""Lanza juegos y mide el tiempo jugado vigilando sus procesos."""
import os
import threading
import time
from typing import Dict, List, Optional, Tuple

import psutil
from PySide6.QtCore import QObject, Signal

from utils.logger import get_logger
from .game_launcher import launch_game
from .models import Game

log = get_logger("tracker")

# Procesos de las plataformas: nunca cuentan como "el juego"
PLATFORM_PROCS = {
    "steam.exe", "steamwebhelper.exe", "steamservice.exe", "epicgameslauncher.exe", "epicwebhelper.exe",
    "ubisoftconnect.exe", "upc.exe", "uplaywebcore.exe", "eadesktop.exe", "eabackgroundservice.exe",
    "galaxyclient.exe", "galaxyclienthelper.exe", "battle.net.exe", "agent.exe", "discord.exe",
    "gameoverlayui.exe", "explorer.exe", "cmd.exe", "conhost.exe",
}
IGNORE_SUBSTR = ("crash", "helper", "unins", "redist", "easyanticheat", "battleye", "beclient",
                 "overlay", "webhelper", "bootstrap")

START_TIMEOUT = 240      # segundos esperando a que el juego aparezca (actualizaciones, etc.)
MIN_SESSION = 15         # sesiones más cortas se descartan


def _norm_dir(path: str) -> str:
    return os.path.normcase(os.path.normpath(path)) + os.sep if path else ""


def matching_pids(game: Game) -> List[int]:
    install = _norm_dir(game.install_dir or (os.path.dirname(game.exe_path) if game.exe_path else ""))
    pname = (game.process_name or "").lower()
    exe_name = os.path.basename(game.exe_path).lower() if game.exe_path else ""
    pids = []
    for p in psutil.process_iter(["pid", "name", "exe"]):
        try:
            name = (p.info["name"] or "").lower()
            exe = p.info["exe"] or ""
        except (psutil.Error, OSError):
            continue
        if not name or name in PLATFORM_PROCS or any(s in name for s in IGNORE_SUBSTR):
            continue
        if (pname and name == pname) or (exe_name and name == exe_name):
            pids.append(p.info["pid"])
        elif install and exe and os.path.normcase(exe).startswith(install):
            pids.append(p.info["pid"])
    return pids


def can_track(game: Game) -> bool:
    return bool(game.install_dir or game.exe_path or game.process_name)


class GameTracker(QObject):
    launched = Signal(int, str)                 # se ha lanzado un juego instalado (game_id, nombre)
    session_started = Signal(int, str)          # game_id, nombre
    session_tick = Signal(int, str, int)        # game_id, nombre, segundos
    session_finished = Signal(int, str, int)    # game_id, nombre, segundos
    notice = Signal(str)                        # mensajes para la barra de estado

    def __init__(self, db, settings):
        super().__init__()
        self.db, self.settings = db, settings
        self._active: Dict[int, Tuple[str, float]] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._threads: List[threading.Thread] = []

    # --------------------------------------------------------------- estado
    def active(self) -> Dict[int, Tuple[str, float]]:
        with self._lock:
            return dict(self._active)

    def is_playing(self, game_id: int) -> bool:
        with self._lock:
            return game_id in self._active

    def current_game_name(self) -> Optional[str]:
        a = self.active()
        if not a:
            return None
        return max(a.values(), key=lambda v: v[1])[0]

    # ------------------------------------------------------------- acciones
    def play(self, game: Game) -> Tuple[bool, str]:
        if self.is_playing(game.id):
            return False, f"{game.name} ya está en ejecución."
        if not game.installed:
            return self.install(game)
        result = launch_game(game)
        if not result.ok:
            self.notice.emit(result.message)
            return False, result.message
        self.launched.emit(game.id, game.name)
        if can_track(game):
            t = threading.Thread(target=self._watch, args=(game,), daemon=True, name=f"track-{game.id}")
            t.start()
            self._threads.append(t)
        else:
            log.info("%s no tiene datos para medir tiempo de juego", game.name)
        return True, result.message

    def close_game(self, game_id: int) -> int:
        """Pide al juego que se cierre (terminate, nunca kill). Devuelve cuántos procesos se contactaron."""
        game = self.db.get_game(game_id)
        if game is None:
            return 0
        n = 0
        for pid in matching_pids(game):
            try:
                psutil.Process(pid).terminate()
                n += 1
            except (psutil.Error, OSError):
                continue
        log.info("Cierre solicitado de %s (%d procesos)", game.name, n)
        return n

    def install(self, game: Game) -> Tuple[bool, str]:
        """Juego de tu cuenta sin instalar: abre la instalación en su plataforma (sin medir tiempo)."""
        from utils.helpers import open_uri
        try:
            if game.launch_uri:
                open_uri(game.launch_uri)
                return True, f"Abriendo la instalación de {game.name} en {game.platform.title()}…"
            from .platform_manager import LAUNCHERS_BY_KEY
            if game.platform in LAUNCHERS_BY_KEY:
                from .platform_manager import PlatformManager
                ok, msg = PlatformManager(self.settings).open(game.platform)
                return ok, f"{msg} Busca «{game.name}» en tu biblioteca para instalarlo."
        except Exception as exc:  # noqa: BLE001
            log.exception("No se pudo abrir la instalación de %s", game.name)
            return False, f"No se pudo abrir la instalación: {exc}"
        return False, f"{game.name} no está instalado y no sé cómo abrir su instalador."

    def stop_all(self) -> None:
        self._stop.set()
        for t in self._threads:
            t.join(timeout=3)

    # ---------------------------------------------------------------- hilo
    def _sleep(self, seconds: float) -> bool:
        """Duerme; devuelve True si se pidió parar."""
        return self._stop.wait(seconds)

    def _watch(self, game: Game) -> None:
        deadline = time.time() + START_TIMEOUT
        found = False
        while time.time() < deadline:
            if matching_pids(game):
                found = True
                break
            if self._sleep(2):
                return
        if not found:
            log.info("No se detectó el proceso de %s; sin seguimiento", game.name)
            return

        started = time.time()
        session_id = self.db.start_session(game.id)
        with self._lock:
            self._active[game.id] = (game.name, started)
        self.session_started.emit(game.id, game.name)
        misses, ticks = 0, 0
        try:
            while True:
                if self._sleep(3):
                    break
                if matching_pids(game):
                    misses = 0
                else:
                    misses += 1
                    if misses >= 2:
                        break
                seconds = int(time.time() - started)
                ticks += 1
                if ticks % 10 == 0:                       # guardado periódico (~30 s)
                    self.db.update_session(session_id, seconds)
                self.session_tick.emit(game.id, game.name, seconds)
        finally:
            seconds = int(time.time() - started)
            with self._lock:
                self._active.pop(game.id, None)
            if seconds < MIN_SESSION:
                self.db.delete_session(session_id)
            else:
                self.db.update_session(session_id, seconds, finished=True)
            self.session_finished.emit(game.id, game.name, seconds)
            log.info("Sesión de %s: %d s", game.name, seconds)
