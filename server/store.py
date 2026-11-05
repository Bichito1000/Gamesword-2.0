"""Capa de datos del servidor de Gamesword (SQLite, sin dependencias externas)."""
import hashlib
import hmac
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import List, Optional

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # sin 0/O/1/I para evitar confusiones
ONLINE_WINDOW = 90                               # segundos sin latido => desconectado
USERNAME_RE = re.compile(r"^[\w .\-]{3,20}$", re.UNICODE)
STATUSES = ("online", "away", "dnd")
PBKDF2_ROUNDS = 200_000
MAX_MESSAGE = 500

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL COLLATE NOCASE UNIQUE,
    friend_code TEXT NOT NULL UNIQUE,
    token_hash TEXT NOT NULL DEFAULT '',
    pw_salt TEXT NOT NULL DEFAULT '',
    pw_hash TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'online',
    playing TEXT,
    last_seen REAL NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS tokens(
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS friendships(
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    friend_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    PRIMARY KEY(user_id, friend_id)
);
CREATE TABLE IF NOT EXISTS groups(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    game TEXT NOT NULL DEFAULT '',
    code TEXT NOT NULL UNIQUE,
    owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS group_members(
    group_id INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    PRIMARY KEY(group_id, user_id)
);
CREATE TABLE IF NOT EXISTS messages(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_group ON messages(group_id, id);
CREATE TABLE IF NOT EXISTS invites(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    to_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    game TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    delivered INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS telemetry(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    install_id TEXT NOT NULL,
    version TEXT NOT NULL,
    event TEXT NOT NULL,
    created_at REAL NOT NULL
);
"""


class StoreError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message, self.status = message, status


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _code() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(6))


def hash_password(password: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ROUNDS).hex()


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as c:
            c.executescript(SCHEMA)
            cols = {r["name"] for r in c.execute("PRAGMA table_info(users)")}
            for col in ("pw_salt", "pw_hash"):          # migración desde el servidor 1.0
                if col not in cols:
                    c.execute(f"ALTER TABLE users ADD COLUMN {col} TEXT NOT NULL DEFAULT ''")
        self._fails = {}      # (ip|usuario) -> [instantes] para bloquear fuerza bruta

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(str(self.path), timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ------------------------------------------------------------- cuentas
    def _new_token(self, c, user_id: int) -> str:
        token = secrets.token_urlsafe(32)
        c.execute("INSERT INTO tokens(token_hash, user_id, created_at) VALUES(?,?,?)",
                  (_hash(token), user_id, time.time()))
        # Máximo 10 sesiones por cuenta
        c.execute("DELETE FROM tokens WHERE user_id=? AND token_hash NOT IN "
                  "(SELECT token_hash FROM tokens WHERE user_id=? ORDER BY created_at DESC LIMIT 10)",
                  (user_id, user_id))
        return token

    def register(self, username: str, password: str) -> dict:
        username = (username or "").strip()
        if not USERNAME_RE.match(username):
            raise StoreError("El nombre debe tener entre 3 y 20 caracteres (letras, números, espacios, . _ -).")
        if len(password or "") < 8:
            raise StoreError("La contraseña debe tener al menos 8 caracteres.")
        salt = secrets.token_bytes(16)
        with self.connect() as c:
            if c.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
                raise StoreError("Ese nombre de usuario ya está en uso.", 409)
            for _ in range(20):
                code = _code()
                if not c.execute("SELECT 1 FROM users WHERE friend_code = ?", (code,)).fetchone():
                    break
            now = time.time()
            uid = c.execute(
                "INSERT INTO users(username, friend_code, pw_salt, pw_hash, last_seen, created_at) "
                "VALUES(?,?,?,?,?,?)",
                (username, code, salt.hex(), hash_password(password, salt), now, now)).lastrowid
            token = self._new_token(c, uid)
        return {"user_id": uid, "username": username, "friend_code": code, "token": token}

    def _throttle(self, key: str) -> None:
        now = time.time()
        fails = [t for t in self._fails.get(key, []) if now - t < 600]
        self._fails[key] = fails
        if len(fails) >= 8:
            raise StoreError("Demasiados intentos fallidos. Espera 10 minutos.", 429)

    def login(self, username: str, password: str, client_key: str = "") -> dict:
        keys = [f"u:{(username or '').lower()}"] + ([f"ip:{client_key}"] if client_key else [])
        for k in keys:
            self._throttle(k)
        with self.connect() as c:
            u = c.execute("SELECT * FROM users WHERE username = ?", ((username or "").strip(),)).fetchone()
            ok = False
            if u and u["pw_hash"]:
                ok = hmac.compare_digest(hash_password(password or "", bytes.fromhex(u["pw_salt"])), u["pw_hash"])
            if not ok:
                for k in keys:
                    self._fails.setdefault(k, []).append(time.time())
                raise StoreError("Usuario o contraseña incorrectos.", 401)
            token = self._new_token(c, u["id"])
        for k in keys:
            self._fails.pop(k, None)
        return {"user_id": u["id"], "username": u["username"], "friend_code": u["friend_code"], "token": token}

    def logout(self, token: str) -> None:
        with self.connect() as c:
            c.execute("DELETE FROM tokens WHERE token_hash = ?", (_hash(token),))

    def user_by_token(self, token: Optional[str]) -> Optional[sqlite3.Row]:
        if not token:
            return None
        with self.connect() as c:
            return c.execute("SELECT u.* FROM tokens t JOIN users u ON u.id = t.user_id WHERE t.token_hash = ?",
                             (_hash(token),)).fetchone()

    def set_status(self, user_id: int, status: str, playing: Optional[str]) -> None:
        if status not in STATUSES:
            raise StoreError("Estado no válido.")
        playing = (playing or "").strip()[:80] or None
        with self.connect() as c:
            c.execute("UPDATE users SET status=?, playing=?, last_seen=? WHERE id=?",
                      (status, playing, time.time(), user_id))

    @staticmethod
    def _public(row: sqlite3.Row) -> dict:
        online = (time.time() - row["last_seen"]) <= ONLINE_WINDOW
        return {"user_id": row["id"], "username": row["username"],
                "status": row["status"] if online else "offline",
                "playing": row["playing"] if online else None}

    # --------------------------------------------------------------- amigos
    def friends(self, user_id: int) -> List[dict]:
        with self.connect() as c:
            rows = c.execute(
                "SELECT u.* FROM friendships f JOIN users u ON u.id = f.friend_id WHERE f.user_id = ? "
                "ORDER BY u.username COLLATE NOCASE", (user_id,)).fetchall()
        out = [self._public(r) for r in rows]
        out.sort(key=lambda f: (f["status"] == "offline", f["username"].lower()))
        return out

    def are_friends(self, a: int, b: int) -> bool:
        with self.connect() as c:
            return c.execute("SELECT 1 FROM friendships WHERE user_id=? AND friend_id=?", (a, b)).fetchone() is not None

    def add_friend(self, user_id: int, code: str) -> dict:
        code = (code or "").strip().upper()
        with self.connect() as c:
            friend = c.execute("SELECT * FROM users WHERE friend_code = ?", (code,)).fetchone()
            if not friend:
                raise StoreError("No existe ningún usuario con ese código.", 404)
            if friend["id"] == user_id:
                raise StoreError("Ese es tu propio código.")
            c.execute("INSERT OR IGNORE INTO friendships(user_id, friend_id) VALUES(?,?)", (user_id, friend["id"]))
            c.execute("INSERT OR IGNORE INTO friendships(user_id, friend_id) VALUES(?,?)", (friend["id"], user_id))
        return self._public(friend)

    def remove_friend(self, user_id: int, friend_id: int) -> None:
        with self.connect() as c:
            c.execute("DELETE FROM friendships WHERE (user_id=? AND friend_id=?) OR (user_id=? AND friend_id=?)",
                      (user_id, friend_id, friend_id, user_id))

    # --------------------------------------------------------------- grupos
    def create_group(self, user_id: int, name: str, game: str) -> dict:
        name, game = (name or "").strip()[:40], (game or "").strip()[:60]
        if len(name) < 2:
            raise StoreError("El grupo necesita un nombre de al menos 2 caracteres.")
        with self.connect() as c:
            for _ in range(20):
                code = _code()
                if not c.execute("SELECT 1 FROM groups WHERE code = ?", (code,)).fetchone():
                    break
            gid = c.execute("INSERT INTO groups(name, game, code, owner_id, created_at) VALUES(?,?,?,?,?)",
                            (name, game, code, user_id, time.time())).lastrowid
            c.execute("INSERT INTO group_members(group_id, user_id) VALUES(?,?)", (gid, user_id))
        return {"id": gid, "name": name, "game": game, "code": code}

    def groups(self, user_id: int) -> List[dict]:
        with self.connect() as c:
            groups = c.execute(
                "SELECT g.* FROM groups g JOIN group_members m ON m.group_id = g.id WHERE m.user_id = ? "
                "ORDER BY g.created_at DESC", (user_id,)).fetchall()
            out = []
            for g in groups:
                members = c.execute(
                    "SELECT u.* FROM group_members m JOIN users u ON u.id = m.user_id WHERE m.group_id = ? "
                    "ORDER BY u.username COLLATE NOCASE", (g["id"],)).fetchall()
                out.append({"id": g["id"], "name": g["name"], "game": g["game"], "code": g["code"],
                            "members": [self._public(m) for m in members]})
        return out

    def join_group(self, user_id: int, code: str) -> dict:
        code = (code or "").strip().upper()
        with self.connect() as c:
            g = c.execute("SELECT * FROM groups WHERE code = ?", (code,)).fetchone()
            if not g:
                raise StoreError("No existe ningún grupo con ese código.", 404)
            c.execute("INSERT OR IGNORE INTO group_members(group_id, user_id) VALUES(?,?)", (g["id"], user_id))
        return {"id": g["id"], "name": g["name"], "game": g["game"], "code": g["code"]}

    def leave_group(self, user_id: int, group_id: int) -> None:
        with self.connect() as c:
            c.execute("DELETE FROM group_members WHERE group_id=? AND user_id=?", (group_id, user_id))
            c.execute("DELETE FROM groups WHERE id=? AND NOT EXISTS "
                      "(SELECT 1 FROM group_members WHERE group_id = groups.id)", (group_id,))

    # ----------------------------------------------------------- chat grupal
    def _require_member(self, c, user_id: int, group_id: int) -> None:
        if not c.execute("SELECT 1 FROM group_members WHERE group_id=? AND user_id=?", (group_id, user_id)).fetchone():
            raise StoreError("No perteneces a ese grupo.", 403)

    def post_message(self, user_id: int, group_id: int, text: str) -> dict:
        text = (text or "").strip()
        if not text:
            raise StoreError("El mensaje está vacío.")
        text = text[:MAX_MESSAGE]
        with self.connect() as c:
            self._require_member(c, user_id, group_id)
            recent = c.execute("SELECT COUNT(*) FROM messages WHERE user_id=? AND created_at > ?",
                               (user_id, time.time() - 10)).fetchone()[0]
            if recent >= 8:
                raise StoreError("Estás escribiendo demasiado rápido.", 429)
            now = time.time()
            mid = c.execute("INSERT INTO messages(group_id, user_id, text, created_at) VALUES(?,?,?,?)",
                            (group_id, user_id, text, now)).lastrowid
            name = c.execute("SELECT username FROM users WHERE id=?", (user_id,)).fetchone()[0]
        return {"id": mid, "user_id": user_id, "username": name, "text": text, "created_at": now}

    def messages(self, user_id: int, group_id: int, after: int = 0, limit: int = 100) -> List[dict]:
        with self.connect() as c:
            self._require_member(c, user_id, group_id)
            rows = c.execute(
                "SELECT m.id, m.user_id, u.username, m.text, m.created_at FROM messages m "
                "JOIN users u ON u.id = m.user_id WHERE m.group_id=? AND m.id>? ORDER BY m.id DESC LIMIT ?",
                (group_id, after, limit)).fetchall()
        return [dict(r) for r in reversed(rows)]

    # ----------------------------------------------------------- invitaciones
    def send_invite(self, from_id: int, to_id: int, game: str, note: str) -> dict:
        if not self.are_friends(from_id, to_id):
            raise StoreError("Solo puedes invitar a tus amigos.", 403)
        with self.connect() as c:
            recent = c.execute("SELECT COUNT(*) FROM invites WHERE from_id=? AND created_at > ?",
                               (from_id, time.time() - 60)).fetchone()[0]
            if recent >= 5:
                raise StoreError("Demasiadas invitaciones seguidas. Espera un minuto.", 429)
            iid = c.execute("INSERT INTO invites(from_id, to_id, game, note, created_at) VALUES(?,?,?,?,?)",
                            (from_id, to_id, (game or "").strip()[:80], (note or "").strip()[:140],
                             time.time())).lastrowid
        return {"id": iid}

    def pending_invites(self, user_id: int) -> List[dict]:
        """Devuelve las invitaciones sin entregar (de los últimos 30 min) y las marca como entregadas."""
        with self.connect() as c:
            rows = c.execute(
                "SELECT i.id, i.from_id, u.username AS from_name, i.game, i.note, i.created_at FROM invites i "
                "JOIN users u ON u.id = i.from_id WHERE i.to_id=? AND i.delivered=0 AND i.created_at > ? "
                "ORDER BY i.id", (user_id, time.time() - 1800)).fetchall()
            c.execute("UPDATE invites SET delivered=1 WHERE to_id=? AND delivered=0", (user_id,))
        return [dict(r) for r in rows]

    # ------------------------------------------------------------ telemetría
    def add_telemetry(self, install_id: str, version: str, event: str) -> None:
        with self.connect() as c:
            c.execute("INSERT INTO telemetry(install_id, version, event, created_at) VALUES(?,?,?,?)",
                      (install_id[:64], version[:20], event[:40], time.time()))
