"""Cliente del servidor de Gamesword (cuentas, amigos, grupos, chat e invitaciones)."""
from typing import List, Optional

import requests


class SocialError(Exception):
    pass


class SocialClient:
    def __init__(self, settings):
        self.settings = settings

    # ------------------------------------------------------------- estado
    @property
    def base_url(self) -> str:
        return (self.settings.get("social.server_url", "") or "").rstrip("/")

    @property
    def registered(self) -> bool:
        return bool(self.settings.get("social.token")) and bool(self.base_url)

    @property
    def enabled(self) -> bool:
        return bool(self.settings.get("social.enabled")) and self.registered

    @property
    def insecure(self) -> bool:
        return self.base_url.startswith("http://") and not any(
            h in self.base_url for h in ("127.0.0.1", "localhost"))

    # ------------------------------------------------------------ peticiones
    def _req(self, method: str, path: str, auth: bool = True, **kwargs):
        if not self.base_url:
            raise SocialError("Configura la dirección del servidor en Ajustes.")
        headers = {"X-Token": self.settings.get("social.token", "")} if auth else {}
        verify = bool(self.settings.get("social.verify_tls", True))
        try:
            r = requests.request(method, self.base_url + path, headers=headers, timeout=6,
                                 verify=verify, **kwargs)
        except requests.exceptions.SSLError:
            raise SocialError("Certificado HTTPS no válido. Si es tu propio servidor con certificado autofirmado, "
                              "desactiva «Verificar certificado» en Ajustes → Online.")
        except requests.ConnectionError:
            raise SocialError("No se pudo conectar con el servidor. ¿Está iniciado?")
        except requests.Timeout:
            raise SocialError("El servidor tardó demasiado en responder.")
        except requests.RequestException as exc:
            raise SocialError(str(exc))
        if r.status_code >= 400:
            try:
                detail = r.json().get("detail", r.text)
            except ValueError:
                detail = r.text
            if isinstance(detail, list):          # error de validación de FastAPI
                detail = "Datos no válidos."
            if r.status_code == 401 and auth:
                self.settings.set("social.token", "")
            raise SocialError(str(detail))
        return r.json() if r.content else None

    def _store_session(self, data: dict) -> dict:
        self.settings.set("social.username", data["username"], save=False)
        self.settings.set("social.user_id", data["user_id"], save=False)
        self.settings.set("social.friend_code", data["friend_code"], save=False)
        self.settings.set("social.enabled", True, save=False)
        self.settings.set("social.token", data["token"])
        return data

    # --------------------------------------------------------------- cuenta
    def register(self, username: str, password: str) -> dict:
        return self._store_session(self._req("POST", "/register", auth=False,
                                             json={"username": username, "password": password}))

    def login(self, username: str, password: str) -> dict:
        return self._store_session(self._req("POST", "/login", auth=False,
                                             json={"username": username, "password": password}))

    def logout(self) -> None:
        try:
            self._req("POST", "/logout")
        except SocialError:
            pass
        self.settings.set("social.token", "")

    # --------------------------------------------------------------- API
    def ping(self, playing: Optional[str]) -> List[dict]:
        """Actualiza estado y devuelve las invitaciones nuevas."""
        share = self.settings.get("social.share_activity", True)
        data = self._req("POST", "/status", json={
            "status": self.settings.get("social.status", "online"),
            "playing": playing if (share and playing) else None})
        return (data or {}).get("invites", [])

    def friends(self) -> List[dict]:
        return self._req("GET", "/friends")

    def add_friend(self, code: str) -> dict:
        return self._req("POST", "/friends/add", json={"friend_code": code.strip().upper()})

    def remove_friend(self, friend_id: int) -> None:
        self._req("DELETE", f"/friends/{friend_id}")

    def invite(self, friend_id: int, game: str, note: str = "") -> None:
        self._req("POST", "/invites", json={"to_user_id": friend_id, "game": game, "note": note})

    def groups(self) -> List[dict]:
        return self._req("GET", "/groups")

    def create_group(self, name: str, game: str) -> dict:
        return self._req("POST", "/groups", json={"name": name, "game": game})

    def join_group(self, code: str) -> dict:
        return self._req("POST", "/groups/join", json={"code": code.strip().upper()})

    def leave_group(self, group_id: int) -> None:
        self._req("POST", f"/groups/{group_id}/leave")

    def messages(self, group_id: int, after: int = 0) -> List[dict]:
        return self._req("GET", f"/groups/{group_id}/messages", params={"after": after})

    def send_message(self, group_id: int, text: str) -> dict:
        return self._req("POST", f"/groups/{group_id}/messages", json={"text": text})
