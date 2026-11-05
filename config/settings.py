"""Configuración persistente en data/settings.json."""
import copy
import json
import threading
from pathlib import Path

from core import secrets_store
from utils.logger import get_logger
from utils.paths import data_dir

log = get_logger("settings")

VERSION = "2.0.0"

# Estos valores van al Administrador de credenciales de Windows si `keyring` está disponible
SECRET_KEYS = {"ai.api_key", "social.token", "steam.api_key", "covers.rawg_key"}

DEFAULTS = {
    "app": {
        "theme": "neon_purple",
        "auto_scan_on_start": True,
        "fetch_covers": True,
        "minimize_on_game_launch": False,
        "start_with_windows": False,
        "start_minimized": False,
        "close_to_tray": False,
        "gamepad": True,
        "hotkeys": True,
        "sync_owned": True,
        "compact": False,
        "accent": "",
        "accent2": "",
        "auto_backup": True,
        "last_backup": "",
        "check_updates": True,
        "update_url": "",
        "telemetry": False,
        "install_id": "",
        "version": VERSION,
    },
    "profile": {"username": "", "avatar": "", "bio": ""},
    "ai": {
        "memory_enabled": True,
        "memory_limit": 30,
        "custom_commands": [],
        "provider": "openai",
        "api_key": "",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "temperature": 0.7,
        "use_tools": True,
        "stream": True,
    },
    "voice": {
        "speak_responses": False,
        "rate": 185,
        "volume": 0.9,
        "language": "es-ES",
        "stt_engine": "google",
        "whisper_model": "base",
        "wake_word": False,
    },
    "steam": {"api_key": "", "steam_id": ""},
    "covers": {"rawg_key": ""},
    "discord": {"app_id": ""},
    "license": {"key": ""},
    "launchers": {"paths": {}},
    "social": {
        "enabled": False,
        "server_url": "http://127.0.0.1:8000",
        "username": "",
        "user_id": None,
        "token": "",
        "friend_code": "",
        "status": "online",
        "share_activity": True,
        "verify_tls": True,
        "last_invite_id": 0,
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


class Settings:
    def __init__(self, path: Path = None):
        self.path = Path(path) if path else data_dir() / "settings.json"
        self._lock = threading.RLock()
        self._data = copy.deepcopy(DEFAULTS)
        self.load()

    def load(self) -> None:
        with self._lock:
            if self.path.exists():
                try:
                    loaded = json.loads(self.path.read_text(encoding="utf-8"))
                    self._data = _deep_merge(DEFAULTS, loaded)
                except (OSError, json.JSONDecodeError) as exc:
                    log.warning("No se pudo leer settings.json (%s); se usan valores por defecto", exc)
            self._migrate_secrets()

    def _migrate_secrets(self) -> None:
        """Mueve claves en texto plano de settings.json al almacén seguro (si existe)."""
        if not secrets_store.available():
            return
        moved = False
        for key in SECRET_KEYS:
            value = self._raw_get(key)
            if value and secrets_store.set(key, value):
                self._raw_set(key, "")
                moved = True
        if moved:
            self.save()

    def _raw_get(self, dotted: str, default=None):
        node = self._data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def _raw_set(self, dotted: str, value) -> None:
        parts = dotted.split(".")
        node = self._data
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value

    def export_public(self) -> dict:
        """Ajustes sin ningún secreto (para copias de seguridad)."""
        import copy as _copy
        data = _copy.deepcopy(self._data)
        for key in SECRET_KEYS:
            parts = key.split(".")
            node = data
            for part in parts[:-1]:
                node = node.get(part, {})
            node.pop(parts[-1], None)
        data.get("social", {}).pop("user_id", None)
        return data

    def import_public(self, data: dict) -> int:
        """Aplica ajustes de una copia sin tocar claves ni la sesión del servidor. Devuelve cuántos cambió."""
        skip = SECRET_KEYS | {"social.user_id", "social.friend_code", "app.install_id"}
        n = 0

        def walk(prefix, node):
            nonlocal n
            for k, v in node.items():
                dotted = f"{prefix}{k}"
                if dotted in skip:
                    continue
                if isinstance(v, dict) and dotted not in ("launchers.paths",):
                    walk(dotted + ".", v)
                else:
                    self.set(dotted, v, save=False)
                    n += 1
        if isinstance(data, dict):
            walk("", data)
        self.save()
        return n

    @property
    def secrets_secure(self) -> bool:
        return secrets_store.available()

    def save(self) -> None:
        with self._lock:
            try:
                tmp = self.path.with_suffix(".tmp")
                tmp.write_text(json.dumps(self._data, indent=2, ensure_ascii=False), encoding="utf-8")
                tmp.replace(self.path)
            except OSError as exc:
                log.error("No se pudo guardar settings.json: %s", exc)

    def get(self, dotted: str, default=None):
        with self._lock:
            if dotted in SECRET_KEYS:
                stored = secrets_store.get(dotted)
                if stored:
                    return stored
            return self._raw_get(dotted, default)

    def set(self, dotted: str, value, save: bool = True) -> None:
        with self._lock:
            if dotted in SECRET_KEYS and secrets_store.set(dotted, value or ""):
                self._raw_set(dotted, "")
            else:
                self._raw_set(dotted, value)
        if save:
            self.save()


_instance = None


def load_settings() -> Settings:
    global _instance
    if _instance is None:
        _instance = Settings()
    return _instance
