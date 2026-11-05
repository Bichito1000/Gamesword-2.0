"""Servidor FastAPI de Gamesword: cuentas, amigos, estados, grupos con chat, invitaciones y telemetría opcional.

Uso local o en red de confianza por defecto. Para Internet: ejecútalo con HTTPS
(python -m server --ssl-certfile cert.pem --ssl-keyfile key.pem, o detrás de Caddy/Nginx).
"""
import os
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .store import Store, StoreError

DB_PATH = Path(os.environ.get("GAMESWORD_SERVER_DB", Path(__file__).resolve().parent.parent / "data" / "server.db"))
store = Store(DB_PATH)
app = FastAPI(title="Gamesword Server", version="1.1.0")

_register_hits = defaultdict(deque)   # IP -> instantes de registro


def _ip(request: Request) -> str:
    return request.client.host if request.client else "?"


@app.exception_handler(StoreError)
async def store_error_handler(_request: Request, exc: StoreError):
    return JSONResponse(status_code=exc.status, content={"detail": exc.message})


def current_user(x_token: Optional[str] = Header(default=None)):
    user = store.user_by_token(x_token)
    if not user:
        raise HTTPException(status_code=401, detail="Sesión no válida. Inicia sesión de nuevo.")
    return user


class AuthBody(BaseModel):
    username: str
    password: str


class StatusBody(BaseModel):
    status: str = "online"
    playing: Optional[str] = None


class FriendBody(BaseModel):
    friend_code: str


class GroupBody(BaseModel):
    name: str
    game: str = ""


class CodeBody(BaseModel):
    code: str


class MessageBody(BaseModel):
    text: str


class InviteBody(BaseModel):
    to_user_id: int
    game: str = ""
    note: str = ""


class TelemetryBody(BaseModel):
    install_id: str
    version: str
    event: str


@app.get("/health")
def health():
    return {"ok": True, "service": "gamesword", "version": "1.1.0"}


@app.post("/register")
def register(body: AuthBody, request: Request):
    hits = _register_hits[_ip(request)]
    now = time.time()
    while hits and now - hits[0] > 600:
        hits.popleft()
    if len(hits) >= 10:
        raise HTTPException(status_code=429, detail="Demasiados registros desde tu red. Espera unos minutos.")
    result = store.register(body.username, body.password)
    hits.append(now)
    return result


@app.post("/login")
def login(body: AuthBody, request: Request):
    return store.login(body.username, body.password, _ip(request))


@app.post("/logout")
def logout(x_token: Optional[str] = Header(default=None), user=Depends(current_user)):
    store.logout(x_token)
    return {"ok": True}


@app.get("/me")
def me(user=Depends(current_user)):
    return {"user_id": user["id"], "username": user["username"], "friend_code": user["friend_code"]}


@app.post("/status")
def status(body: StatusBody, user=Depends(current_user)):
    store.set_status(user["id"], body.status, body.playing)
    return {"ok": True, "invites": store.pending_invites(user["id"])}


@app.get("/friends")
def friends(user=Depends(current_user)):
    return store.friends(user["id"])


@app.post("/friends/add")
def add_friend(body: FriendBody, user=Depends(current_user)):
    return store.add_friend(user["id"], body.friend_code)


@app.delete("/friends/{friend_id}")
def remove_friend(friend_id: int, user=Depends(current_user)):
    store.remove_friend(user["id"], friend_id)
    return {"ok": True}


@app.post("/invites")
def send_invite(body: InviteBody, user=Depends(current_user)):
    return store.send_invite(user["id"], body.to_user_id, body.game, body.note)


@app.get("/groups")
def groups(user=Depends(current_user)):
    return store.groups(user["id"])


@app.post("/groups")
def create_group(body: GroupBody, user=Depends(current_user)):
    return store.create_group(user["id"], body.name, body.game)


@app.post("/groups/join")
def join_group(body: CodeBody, user=Depends(current_user)):
    return store.join_group(user["id"], body.code)


@app.post("/groups/{group_id}/leave")
def leave_group(group_id: int, user=Depends(current_user)):
    store.leave_group(user["id"], group_id)
    return {"ok": True}


@app.get("/groups/{group_id}/messages")
def get_messages(group_id: int, after: int = 0, user=Depends(current_user)):
    return store.messages(user["id"], group_id, after)


@app.post("/groups/{group_id}/messages")
def post_message(group_id: int, body: MessageBody, user=Depends(current_user)):
    return store.post_message(user["id"], group_id, body.text)


@app.post("/telemetry")
def telemetry(body: TelemetryBody):
    store.add_telemetry(body.install_id, body.version, body.event)
    return {"ok": True}
