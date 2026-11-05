"""Importa las horas jugadas desde la API oficial de Steam (necesita tu clave y tu SteamID64)."""
from dataclasses import dataclass

import requests

from .models import Game

API = "https://api.steampowered.com/IPlayerService/GetOwnedGames/v0001/"


class SteamImportError(Exception):
    pass


@dataclass
class ImportResult:
    matched: int = 0
    updated: int = 0
    added: int = 0
    total_owned: int = 0


def import_playtime(db, api_key: str, steam_id: str, add_owned: bool = False) -> ImportResult:
    api_key, steam_id = (api_key or "").strip(), (steam_id or "").strip()
    if not api_key or not steam_id.isdigit() or len(steam_id) < 15:
        raise SteamImportError("Indica tu clave de la API de Steam y tu SteamID64 (17 dígitos) en Ajustes.")
    try:
        r = requests.get(API, timeout=15, params={
            "key": api_key, "steamid": steam_id, "include_appinfo": 1,
            "include_played_free_games": 1, "format": "json"})
    except requests.RequestException:
        raise SteamImportError("No se pudo contactar con Steam. Revisa tu conexión.")
    if r.status_code in (401, 403):
        raise SteamImportError("Steam rechazó la clave de API. Comprueba que es correcta.")
    if r.status_code != 200:
        raise SteamImportError(f"Steam respondió con el error {r.status_code}.")
    try:
        games = r.json().get("response", {}).get("games")
    except ValueError:
        raise SteamImportError("Respuesta no válida de Steam.")
    if games is None:
        raise SteamImportError("Steam no devolvió juegos: el SteamID es incorrecto o tu perfil/detalles de "
                               "juego son privados (ponlos en «Público» en la privacidad de Steam).")
    res = ImportResult(total_owned=len(games))
    for item in games:
        appid, name = str(item.get("appid")), item.get("name", "")
        minutes = int(item.get("playtime_forever", 0))
        game = db.find_game("steam", appid)
        if game is None and add_owned and name:
            gid = db.add_game(Game(name=name, platform="steam", external_id=appid, source="auto", installed=0,
                                   launch_uri=f"steam://install/{appid}"))
            game = db.get_game(gid)
            res.added += 1
        if game is None:
            continue
        res.matched += 1
        # Las horas de Steam ya incluyen las sesiones lanzadas desde Gamesword: se restan para no duplicar
        extra = minutes * 60 - db.real_seconds(game.id)
        db.set_imported_seconds(game.id, max(0, extra))
        res.updated += 1
    return res
