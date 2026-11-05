"""Licencias Plus / Pro verificadas sin conexión (firma Ed25519).

Cómo funciona:
  1. Tú (el autor) generas un par de claves con  python tools/license_tool.py keygen
     y pegas la clave PÚBLICA en PUBLIC_KEY_HEX. La privada NO se distribuye jamás.
  2. Para cada cliente:  python tools/license_tool.py issue --tier plus --name "Ana" --days 365
  3. El cliente pega la licencia en Ajustes. Gamesword comprueba la firma y la caducidad.

ENFORCE_LICENSES está en False: mientras no lo actives, todas las funciones están desbloqueadas
y las licencias solo se muestran. Cuando decidas cobrar, ponlo a True.
"""
import base64
import json
import time
from dataclasses import dataclass
from typing import Optional

from . import ed25519

PUBLIC_KEY_HEX = ""          # <- pega aquí tu clave pública (64 caracteres hex)
ENFORCE_LICENSES = False     # <- True para bloquear funciones Plus/Pro sin licencia

TIERS = {"free": 0, "plus": 1, "pro": 2}
FEATURES = {                 # característica -> nivel mínimo
    "ai_chat": "plus",
    "ai_voice_local": "plus",
    "themes": "plus",
    "steam_import": "plus",
    "performance": "pro",
    "gamepad": "pro",
    "rich_presence": "pro",
    "wake_word": "pro",
}


@dataclass
class LicenseInfo:
    valid: bool
    tier: str = "free"
    name: str = ""
    expires: Optional[float] = None
    message: str = ""


def _b64d(s: str) -> bytes:
    s = s.strip().replace("\n", "").replace(" ", "")
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def encode_license(payload: dict, signature: bytes) -> str:
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(body).decode().rstrip("=") + "." + \
        base64.urlsafe_b64encode(signature).decode().rstrip("=")


def verify_license(text: str, public_hex: str = None, now: float = None) -> LicenseInfo:
    public_hex = PUBLIC_KEY_HEX if public_hex is None else public_hex
    if not text or not text.strip():
        return LicenseInfo(False, message="Sin licencia (versión gratuita).")
    if len(public_hex) != 64:
        return LicenseInfo(False, message="Esta compilación no tiene clave pública de licencias configurada.")
    try:
        body_b64, sig_b64 = text.strip().split(".")
        body, sig = _b64d(body_b64), _b64d(sig_b64)
        if not ed25519.verify(bytes.fromhex(public_hex), body, sig):
            return LicenseInfo(False, message="La licencia no es auténtica.")
        data = json.loads(body.decode("utf-8"))
    except (ValueError, TypeError, KeyError):
        return LicenseInfo(False, message="Formato de licencia no válido.")
    tier = data.get("tier", "free")
    if tier not in TIERS:
        return LicenseInfo(False, message="Nivel de licencia desconocido.")
    exp = data.get("exp")
    if exp is not None and (now or time.time()) > float(exp):
        return LicenseInfo(False, tier, data.get("name", ""), exp, "La licencia ha caducado.")
    return LicenseInfo(True, tier, data.get("name", ""), exp, f"Licencia {tier.title()} activa.")


class LicenseManager:
    def __init__(self, settings):
        self.settings = settings

    def info(self) -> LicenseInfo:
        return verify_license(self.settings.get("license.key", ""))

    def tier(self) -> str:
        i = self.info()
        return i.tier if i.valid else "free"

    def allows(self, feature: str) -> bool:
        if not ENFORCE_LICENSES:
            return True
        need = FEATURES.get(feature, "free")
        return TIERS[self.tier()] >= TIERS[need]

    def activate(self, text: str) -> LicenseInfo:
        info = verify_license(text)
        if info.valid:
            self.settings.set("license.key", text.strip())
        return info
