"""Sincroniza la biblioteca COMPLETA: instalados (detección local) + todo lo que posees en tus cuentas."""
from collections import Counter
from typing import Callable, List, Optional

from config.settings import Settings
from utils.logger import get_logger
from . import epic_import, galaxy_import, game_detector
from .steam_import import SteamImportError, import_playtime

log = get_logger("sync")


def sync_all(db, settings: Settings, progress: Optional[Callable[[str], None]] = None) -> List[str]:
    """Devuelve líneas legibles con el resultado de cada fuente."""
    say = progress or (lambda _m: None)
    lines: List[str] = []

    # 1) Instalados (siempre)
    say("Buscando juegos instalados…")
    found = game_detector.detect_all()
    new_installed = db.upsert_detected(found)
    by_platform = Counter(g.platform for g in found)
    for platform, ids in {p: {g.external_id for g in found if g.platform == p} for p in by_platform}.items():
        db.mark_uninstalled(platform, ids)
    lines.append(f"Instalados: {len(found)} detectados, {new_installed} nuevos.")

    if not settings.get("app.sync_owned", True):
        return lines

    # 2) Steam: todo lo que posees
    key = (settings.get("steam.api_key", "") or "").strip()
    sid = (settings.get("steam.steam_id", "") or "").strip() or (game_detector.steam_user_id() or "")
    if key and sid:
        say("Leyendo tu biblioteca de Steam…")
        try:
            r = import_playtime(db, key, sid, add_owned=True)
            lines.append(f"Steam: {r.total_owned} juegos en tu cuenta, {r.added} añadidos sin instalar, "
                         f"horas actualizadas en {r.updated}.")
        except SteamImportError as exc:
            lines.append(f"Steam: {exc}")
    else:
        lines.append("Steam: para ver los juegos que no tienes instalados añade tu clave de API en Ajustes "
                     "→ Biblioteca (el SteamID se detecta solo).")

    # 3) GOG Galaxy 2.0 (Steam, Epic, Ubisoft, EA, Xbox, Battle.net, GOG)
    say("Buscando GOG Galaxy…")
    owned = galaxy_import.read_owned()
    if owned:
        added = db.upsert_detected(owned)
        lines.append(f"GOG Galaxy: {len(owned)} juegos en tus cuentas conectadas, {added} nuevos.")
    elif galaxy_import.db_path().exists():
        lines.append("GOG Galaxy: encontrado, pero no pude leer su biblioteca.")

    # 4) Epic con legendary
    say("Buscando biblioteca de Epic…")
    try:
        epic = epic_import.read_owned()
        added = db.upsert_detected(epic)
        lines.append(f"Epic (legendary): {len(epic)} juegos en tu cuenta, {added} nuevos.")
    except epic_import.EpicImportError as exc:
        lines.append(f"Epic: {exc}")
    return lines
