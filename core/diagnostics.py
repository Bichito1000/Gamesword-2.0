"""Informe de diagnóstico: un .zip con logs, versiones y ajustes SIN claves, para adjuntar al pedir soporte."""
import json
import platform
import sys
import zipfile
from datetime import datetime
from pathlib import Path

from utils.paths import data_dir, logs_dir

REDACT = ("api_key", "token", "rawg_key", "key", "app_id", "install_id")


def _redact(node):
    if isinstance(node, dict):
        return {k: ("***" if any(r == k or k.endswith("_key") for r in REDACT) and node[k] else _redact(v))
                for k, v in node.items()}
    return node


def create_report(settings, ctx=None) -> Path:
    out = data_dir() / f"diagnostico_{datetime.now():%Y%m%d_%H%M%S}.zip"
    info = {
        "gamesword": settings.get("app.version"), "python": sys.version, "sistema": platform.platform(),
        "frozen": bool(getattr(sys, "frozen", False)),
    }
    try:
        import PySide6
        info["pyside6"] = PySide6.__version__
    except Exception:  # noqa: BLE001
        pass
    if ctx is not None:
        try:
            info["juegos"] = ctx.db.count_games()
            info["lanzadores_detectados"] = ctx.platforms.installed_keys()
            info["voz_tts"] = ctx.voice.tts_available
            info["voz_micro"] = ctx.voice.stt_available
        except Exception as exc:  # noqa: BLE001
            info["error_recogiendo_datos"] = str(exc)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("info.json", json.dumps(info, indent=2, ensure_ascii=False))
        z.writestr("ajustes_sin_claves.json",
                   json.dumps(_redact(settings._data), indent=2, ensure_ascii=False))
        for log in sorted(Path(logs_dir()).glob("gamesword.log*")):
            z.write(log, f"logs/{log.name}")
    return out
