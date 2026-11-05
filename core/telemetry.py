"""Telemetría OPCIONAL y anónima (desactivada por defecto).

Si el usuario la activa, envía únicamente: un identificador aleatorio de instalación, la versión y el nombre
de un evento («start»). Nada de juegos, nombres, rutas ni contenido del chat.
"""
import threading
import uuid

import requests

from utils.logger import get_logger

log = get_logger("telemetry")


def install_id(settings) -> str:
    iid = settings.get("app.install_id", "")
    if not iid:
        iid = uuid.uuid4().hex
        settings.set("app.install_id", iid)
    return iid


def send_event(settings, event: str) -> None:
    if not settings.get("app.telemetry", False):
        return
    base = (settings.get("app.update_url", "") or "").strip()
    server = (settings.get("social.server_url", "") or "").rstrip("/")
    url = (server + "/telemetry") if server else ""
    if not url or not url.startswith(("http://", "https://")):
        return
    payload = {"install_id": install_id(settings), "version": settings.get("app.version", ""), "event": event}
    verify = bool(settings.get("social.verify_tls", True))

    def run():
        try:
            requests.post(url, json=payload, timeout=5, verify=verify)
        except requests.RequestException:
            pass
    threading.Thread(target=run, daemon=True).start()
