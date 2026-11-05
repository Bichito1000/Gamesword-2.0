"""Descarga y caché de portadas (CDN público de Steam)."""
import threading
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

import requests
from PySide6.QtCore import QObject, Signal

from utils.helpers import normalize
from utils.logger import get_logger
from utils.paths import covers_dir
from .models import Game

log = get_logger("covers")

CDN = "https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/{file}"
SEARCH = "https://store.steampowered.com/api/storesearch/"
HEADERS = {"User-Agent": "Gamesword/1.0"}


def _download(url: str, dest: Path) -> bool:
    try:
        r = requests.get(url, timeout=8, headers=HEADERS)
        if r.status_code == 200 and r.content and r.headers.get("content-type", "").startswith("image"):
            dest.write_bytes(r.content)
            return True
    except requests.RequestException:
        pass
    return False


def steam_cover_for_appid(appid) -> Optional[Path]:
    """Portada vertical (o cabecera como alternativa), en caché."""
    dest = covers_dir() / f"steam_{appid}.jpg"
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    for f in ("library_600x900.jpg", "header.jpg"):
        if _download(CDN.format(appid=appid, file=f), dest):
            return dest
    return None


def find_steam_appid(name: str) -> Optional[str]:
    try:
        r = requests.get(SEARCH, params={"term": name, "cc": "es", "l": "spanish"}, timeout=8, headers=HEADERS)
        items = r.json().get("items", [])
    except (requests.RequestException, ValueError):
        return None
    target = normalize(name)
    for it in items[:5]:
        if SequenceMatcher(None, normalize(it.get("name", "")), target).ratio() >= 0.88:
            return str(it["id"])
    return None


def rawg_cover(name: str, key: str, dest: Path) -> Optional[Path]:
    """Portada alternativa desde RAWG (clave gratuita en rawg.io/apidocs) para juegos que no están en Steam."""
    try:
        r = requests.get("https://api.rawg.io/api/games", timeout=8, headers=HEADERS,
                         params={"search": name, "page_size": 3, "key": key})
        results = r.json().get("results", [])
    except (requests.RequestException, ValueError):
        return None
    target = normalize(name)
    for it in results:
        if it.get("background_image") and SequenceMatcher(None, normalize(it.get("name", "")), target).ratio() >= 0.85:
            return dest if _download(it["background_image"], dest) else None
    return None


class CoverFetcher(QObject):
    cover_ready = Signal(int, str)        # game_id, ruta
    appid_cover_ready = Signal(int, str)  # appid (para Descubrir), ruta

    def __init__(self, db, settings):
        super().__init__()
        self.db, self.settings = db, settings
        self._pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="covers")
        self._attempted = set()
        self._lock = threading.Lock()

    def request(self, game: Game) -> None:
        if not self.settings.get("app.fetch_covers", True):
            return
        if game.cover_path and Path(game.cover_path).exists():
            return
        with self._lock:
            if game.id in self._attempted:
                return
            self._attempted.add(game.id)
        self._pool.submit(self._fetch_game, game)

    def request_appid(self, appid: int) -> None:
        key = ("app", appid)
        with self._lock:
            if key in self._attempted:
                return
            self._attempted.add(key)
        self._pool.submit(self._fetch_appid, appid)

    def _fetch_game(self, game: Game) -> None:
        try:
            appid = game.external_id if game.platform == "steam" else find_steam_appid(game.name)
            path = steam_cover_for_appid(appid) if appid else None
            if not path:
                key = (self.settings.get("covers.rawg_key", "") or "").strip()
                if key:
                    path = rawg_cover(game.name, key, covers_dir() / f"game_{game.id}.jpg")
            if path:
                self.db.set_cover(game.id, str(path))
                self.cover_ready.emit(game.id, str(path))
        except Exception:  # noqa: BLE001
            log.exception("Error obteniendo portada de %s", game.name)

    def _fetch_appid(self, appid: int) -> None:
        path = steam_cover_for_appid(appid)
        if path:
            self.appid_cover_ready.emit(appid, str(path))

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)
