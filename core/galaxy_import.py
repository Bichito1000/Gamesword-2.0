"""Biblioteca completa de TODAS tus plataformas vía GOG Galaxy 2.0 (si lo usas con integraciones).

GOG Galaxy 2.0 agrega en una base de datos local los juegos que posees en Steam, Epic, Ubisoft, EA, Xbox,
Battle.net…, instalados o no. Gamesword lee esa base de datos (copia temporal, solo lectura) y no toca nada más.
Es un mecanismo no documentado por GOG: si cambia el esquema, devolverá lista vacía en vez de fallar.
"""
import json
import os
import shutil
import sqlite3
import tempfile
from pathlib import Path
from typing import List

from utils.logger import get_logger
from .models import DetectedGame

log = get_logger("galaxy")

PREFIX = {"steam": "steam", "epic": "epic", "uplay": "ubisoft", "origin": "ea", "gog": "gog",
          "xboxone": "xbox", "battlenet": "battlenet", "rockstar": "rockstar"}


def db_path() -> Path:
    return Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "GOG.com" / "Galaxy" / "storage" / "galaxy-2.0.db"


def read_owned(path: Path = None) -> List[DetectedGame]:
    path = Path(path) if path else db_path()
    if not path.exists():
        return []
    tmp = Path(tempfile.mkdtemp()) / "galaxy.db"
    try:
        shutil.copy2(path, tmp)                       # Galaxy puede tener el archivo bloqueado
        conn = sqlite3.connect(str(tmp))
        try:
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            owned_tbl = next((t for t in ("LibraryReleases", "OwnedGames") if t in tables), None)
            if not owned_tbl or not {"GamePieces", "GamePieceTypes"} <= tables:
                log.info("Esquema de GOG Galaxy no reconocido")
                return []
            hidden = set()
            if "UserReleaseProperties" in tables:
                hidden = {r[0] for r in conn.execute("SELECT releaseKey FROM UserReleaseProperties WHERE isHidden=1")}
            owned = {r[0] for r in conn.execute(f"SELECT releaseKey FROM {owned_tbl}")}
            titles = {}
            for kind in ("title", "originalTitle"):      # «title» tiene prioridad sobre «originalTitle»
                for key, value in conn.execute(
                        "SELECT gp.releaseKey, gp.value FROM GamePieces gp JOIN GamePieceTypes t "
                        "ON t.id = gp.gamePieceTypeId WHERE t.type = ?", (kind,)):
                    try:
                        titles[key] = json.loads(value)["title"]
                    except (ValueError, KeyError, TypeError):
                        continue
        finally:
            conn.close()
    except (sqlite3.Error, OSError) as exc:
        log.warning("No se pudo leer GOG Galaxy: %s", exc)
        return []
    out = []
    for key in sorted(owned - hidden):
        prefix, _, ext = key.partition("_")
        platform = PREFIX.get(prefix)
        if platform and ext and titles.get(key):
            out.append(DetectedGame(name=titles[key], platform=platform, external_id=ext,
                                    launch_uri=f"uplay://launch/{ext}/0" if platform == "ubisoft" else "",
                                    installed=False))
    return out
