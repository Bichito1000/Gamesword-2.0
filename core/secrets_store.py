"""Guarda secretos (clave de IA, token del servidor) en el Administrador de credenciales de Windows.

Usa la librería opcional `keyring`. Si no está disponible, cae a settings.json (texto plano) y lo indica.
"""
from utils.logger import get_logger

log = get_logger("secrets")
SERVICE = "Gamesword"

try:
    import keyring
    from keyring.errors import KeyringError
except Exception:  # noqa: BLE001
    keyring = None
    KeyringError = Exception


def available() -> bool:
    if keyring is None:
        return False
    try:
        name = keyring.get_keyring().__class__.__name__.lower()
        return "fail" not in name and "null" not in name
    except Exception:  # noqa: BLE001
        return False


def get(name: str) -> str:
    if not available():
        return ""
    try:
        return keyring.get_password(SERVICE, name) or ""
    except KeyringError:
        return ""


def set(name: str, value: str) -> bool:      # noqa: A001
    if not available():
        return False
    try:
        if value:
            keyring.set_password(SERVICE, name, value)
        else:
            try:
                keyring.delete_password(SERVICE, name)
            except KeyringError:
                pass
        return True
    except KeyringError:
        log.warning("No se pudo guardar el secreto %s en el almacén seguro", name)
        return False
