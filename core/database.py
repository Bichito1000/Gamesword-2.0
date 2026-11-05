"""Base de datos SQLite (una conexión por operación: segura entre hilos)."""
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, List, Optional

from utils.helpers import normalize
from utils.logger import get_logger
from utils.paths import data_dir
from .models import DetectedGame, Game

log = get_logger("db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS games(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    platform TEXT NOT NULL DEFAULT 'other',
    exe_path TEXT NOT NULL DEFAULT '',
    launch_uri TEXT NOT NULL DEFAULT '',
    install_dir TEXT NOT NULL DEFAULT '',
    process_name TEXT NOT NULL DEFAULT '',
    cover_path TEXT NOT NULL DEFAULT '',
    external_id TEXT NOT NULL DEFAULT '',
    tags TEXT NOT NULL DEFAULT '',
    favorite INTEGER NOT NULL DEFAULT 0,
    notes TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'manual',
    hidden INTEGER NOT NULL DEFAULT 0,
    installed INTEGER NOT NULL DEFAULT 1,
    added_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_games_ext ON games(platform, external_id) WHERE external_id != '';

CREATE TABLE IF NOT EXISTS sessions(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    seconds INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_sessions_game ON sessions(game_id);
CREATE INDEX IF NOT EXISTS idx_sessions_start ON sessions(started_at);

CREATE TABLE IF NOT EXISTS collections(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS collection_games(
    collection_id INTEGER NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    game_id INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    PRIMARY KEY(collection_id, game_id)
);

CREATE TABLE IF NOT EXISTS achievements(
    key TEXT PRIMARY KEY,
    unlocked_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS challenges(
    key TEXT NOT NULL,
    period TEXT NOT NULL,
    completed_at TEXT NOT NULL,
    PRIMARY KEY(key, period)
);
CREATE TABLE IF NOT EXISTS counters(
    key TEXT PRIMARY KEY,
    value INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS activity(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    text TEXT NOT NULL,
    xp INTEGER NOT NULL DEFAULT 0,
    ref TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_activity_kind ON activity(kind, created_at);
CREATE TABLE IF NOT EXISTS ai_memory(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chat_history(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""

_ORDERS = {
    "name": "LOWER(g.name) ASC",
    "played": "total_seconds DESC, LOWER(g.name) ASC",
    "recent": "last_played IS NULL, last_played DESC, LOWER(g.name) ASC",
    "added": "g.added_at DESC",
}


IMPORT_TS = "2000-01-01T00:00:00"   # sesión sintética con las horas importadas de Steam


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class DatabaseManager:
    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else data_dir() / "gamesword.db"

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

    # ------------------------------------------------------------------ init
    def init(self) -> None:
        with self.connect() as c:
            c.execute("PRAGMA journal_mode = WAL")
            c.executescript(SCHEMA)
            cols = {r["name"] for r in c.execute("PRAGMA table_info(games)")}
            if "installed" not in cols:                       # migración desde la 1.0
                c.execute("ALTER TABLE games ADD COLUMN installed INTEGER NOT NULL DEFAULT 1")
            # Sesiones que quedaron abiertas por un cierre inesperado
            c.execute(
                "UPDATE sessions SET ended_at = started_at WHERE ended_at IS NULL"
            )
        log.info("Base de datos lista en %s", self.path)

    # ----------------------------------------------------------------- games
    _SELECT = (
        "SELECT g.*, COALESCE(SUM(s.seconds), 0) AS total_seconds, "
        f"COUNT(CASE WHEN s.started_at != '{IMPORT_TS}' THEN s.id END) AS sessions, "
        f"MAX(CASE WHEN s.started_at != '{IMPORT_TS}' THEN s.started_at END) AS last_played "
        "FROM games g LEFT JOIN sessions s ON s.game_id = g.id "
    )

    def list_games(self, search: str = "", platform: Optional[str] = None,
                   favorites_only: bool = False, order: str = "name",
                   installed: Optional[bool] = None, collection_id: Optional[int] = None) -> List[Game]:
        where, params = ["g.hidden = 0"], []
        if collection_id:
            where.append("g.id IN (SELECT game_id FROM collection_games WHERE collection_id = ?)")
            params.append(collection_id)
        if installed is not None:
            where.append("g.installed = ?")
            params.append(1 if installed else 0)
        if search:
            where.append("(LOWER(g.name) LIKE ? OR LOWER(g.tags) LIKE ?)")
            params += [f"%{search.lower()}%"] * 2
        if platform and platform != "all":
            where.append("g.platform = ?")
            params.append(platform)
        if favorites_only:
            where.append("g.favorite = 1")
        sql = (self._SELECT + "WHERE " + " AND ".join(where) +
               " GROUP BY g.id ORDER BY " + _ORDERS.get(order, _ORDERS["name"]))
        with self.connect() as c:
            return [Game.from_row(r) for r in c.execute(sql, params)]

    def get_game(self, game_id: int) -> Optional[Game]:
        with self.connect() as c:
            row = c.execute(self._SELECT + "WHERE g.id = ? GROUP BY g.id", (game_id,)).fetchone()
        return Game.from_row(row) if row and row["id"] is not None else None

    def add_game(self, game: Game) -> int:
        with self.connect() as c:
            cur = c.execute(
                "INSERT INTO games(name, platform, exe_path, launch_uri, install_dir, process_name, "
                "cover_path, external_id, tags, favorite, notes, source, installed, added_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (game.name.strip(), game.platform, game.exe_path, game.launch_uri, game.install_dir,
                 game.process_name, game.cover_path, game.external_id, game.tags, game.favorite,
                 game.notes, game.source, int(game.installed), game.added_at or _now()),
            )
            return int(cur.lastrowid)

    def update_game(self, game: Game) -> None:
        with self.connect() as c:
            c.execute(
                "UPDATE games SET name=?, platform=?, exe_path=?, launch_uri=?, install_dir=?, "
                "process_name=?, cover_path=?, tags=?, notes=? WHERE id=?",
                (game.name.strip(), game.platform, game.exe_path, game.launch_uri, game.install_dir,
                 game.process_name, game.cover_path, game.tags, game.notes, game.id),
            )

    def delete_game(self, game_id: int) -> None:
        """Los juegos detectados se ocultan (para que un nuevo escaneo no los reimporte)."""
        with self.connect() as c:
            row = c.execute("SELECT source FROM games WHERE id=?", (game_id,)).fetchone()
            if not row:
                return
            if row["source"] == "auto":
                c.execute("UPDATE games SET hidden=1 WHERE id=?", (game_id,))
            else:
                c.execute("DELETE FROM games WHERE id=?", (game_id,))

    def unhide_all(self) -> int:
        with self.connect() as c:
            return c.execute("UPDATE games SET hidden=0 WHERE hidden=1").rowcount

    def toggle_favorite(self, game_id: int) -> None:
        with self.connect() as c:
            c.execute("UPDATE games SET favorite = 1 - favorite WHERE id=?", (game_id,))

    def set_cover(self, game_id: int, path: str) -> None:
        with self.connect() as c:
            c.execute("UPDATE games SET cover_path=? WHERE id=?", (path, game_id))

    def upsert_detected(self, detected: Iterable[DetectedGame]) -> int:
        """Importa juegos detectados (instalados) o de tu cuenta (installed=False). Devuelve cuántos son nuevos."""
        added = 0
        with self.connect() as c:
            by_name = {(r["platform"], normalize(r["name"])): r["id"]
                       for r in c.execute("SELECT id, platform, name FROM games")}
            for d in detected:
                row = None
                if d.external_id:
                    row = c.execute("SELECT id FROM games WHERE platform=? AND external_id=?",
                                    (d.platform, d.external_id)).fetchone()
                gid = row["id"] if row else by_name.get((d.platform, normalize(d.name)))
                if gid:
                    if d.installed:       # lo vemos instalado ahora: actualizar rutas y marcar como instalado
                        c.execute("UPDATE games SET exe_path=?, launch_uri=?, install_dir=?, process_name=?, "
                                  "installed=1 WHERE id=? AND source='auto'",
                                  (d.exe_path, d.launch_uri, d.install_dir, d.process_name, gid))
                        if d.external_id:
                            c.execute("UPDATE games SET external_id=? WHERE id=? AND external_id=''",
                                      (d.external_id, gid))
                    continue
                c.execute(
                    "INSERT INTO games(name, platform, exe_path, launch_uri, install_dir, process_name, "
                    "external_id, tags, source, installed, added_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (d.name, d.platform, d.exe_path, d.launch_uri, d.install_dir, d.process_name,
                     d.external_id, d.tags, "auto", int(d.installed), _now()))
                by_name[(d.platform, normalize(d.name))] = c.execute("SELECT last_insert_rowid()").fetchone()[0]
                added += 1
        return added

    def mark_uninstalled(self, platform: str, keep_external_ids) -> int:
        """Los juegos automáticos de una plataforma que ya no aparecen instalados pasan a «no instalado»."""
        keep = set(keep_external_ids)
        n = 0
        with self.connect() as c:
            for r in c.execute("SELECT id, external_id FROM games WHERE platform=? AND source='auto' "
                               "AND installed=1 AND external_id != ''", (platform,)).fetchall():
                if r["external_id"] not in keep:
                    c.execute("UPDATE games SET installed=0 WHERE id=?", (r["id"],))
                    n += 1
        return n

    def count_installed(self) -> int:
        with self.connect() as c:
            return c.execute("SELECT COUNT(*) FROM games WHERE hidden=0 AND installed=1").fetchone()[0]

    def count_games(self) -> int:
        with self.connect() as c:
            return c.execute("SELECT COUNT(*) FROM games WHERE hidden=0").fetchone()[0]

    def platforms_in_use(self) -> List[str]:
        with self.connect() as c:
            return [r[0] for r in c.execute(
                "SELECT DISTINCT platform FROM games WHERE hidden=0 ORDER BY platform")]

    # -------------------------------------------------------------- sessions
    def start_session(self, game_id: int) -> int:
        with self.connect() as c:
            return int(c.execute(
                "INSERT INTO sessions(game_id, started_at) VALUES(?, ?)", (game_id, _now())).lastrowid)

    def update_session(self, session_id: int, seconds: int, finished: bool = False) -> None:
        with self.connect() as c:
            if finished:
                c.execute("UPDATE sessions SET seconds=?, ended_at=? WHERE id=?",
                          (int(seconds), _now(), session_id))
            else:
                c.execute("UPDATE sessions SET seconds=? WHERE id=?", (int(seconds), session_id))

    def delete_session(self, session_id: int) -> None:
        with self.connect() as c:
            c.execute("DELETE FROM sessions WHERE id=?", (session_id,))

    # ----------------------------------------------------------------- stats
    @staticmethod
    def _since(days: Optional[int]) -> Optional[str]:
        if days is None:
            return None
        start = (datetime.now() - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return start.isoformat(timespec="seconds")

    def total_seconds(self, days: Optional[int] = None, since: Optional[str] = None) -> int:
        since = since or self._since(days)
        sql = ("SELECT COALESCE(SUM(s.seconds),0) FROM sessions s JOIN games g ON g.id=s.game_id "
               "WHERE g.hidden=0")
        params = []
        if since:
            sql += " AND s.started_at >= ?"
            params.append(since)
        with self.connect() as c:
            return int(c.execute(sql, params).fetchone()[0])

    def week_start(self) -> str:
        now = datetime.now()
        monday = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        return monday.isoformat(timespec="seconds")

    def session_count(self, days: Optional[int] = None) -> int:
        since = self._since(days)
        sql = (f"SELECT COUNT(*) FROM sessions s JOIN games g ON g.id=s.game_id WHERE g.hidden=0 "
               f"AND s.started_at != '{IMPORT_TS}'")
        params = []
        if since:
            sql += " AND s.started_at >= ?"
            params.append(since)
        with self.connect() as c:
            return int(c.execute(sql, params).fetchone()[0])

    def seconds_by_day(self, days: int) -> List[tuple]:
        """[(date_iso, seconds)] de los últimos N días, con ceros incluidos."""
        since = self._since(days)
        with self.connect() as c:
            rows = c.execute(
                "SELECT date(s.started_at) AS d, SUM(s.seconds) AS t FROM sessions s "
                "JOIN games g ON g.id=s.game_id WHERE g.hidden=0 AND s.started_at >= ? GROUP BY d",
                (since,)).fetchall()
        data = {r["d"]: int(r["t"] or 0) for r in rows}
        today = datetime.now().date()
        out = []
        for i in range(days - 1, -1, -1):
            d = (today - timedelta(days=i)).isoformat()
            out.append((d, data.get(d, 0)))
        return out

    def top_games(self, limit: int = 5, days: Optional[int] = None) -> List[tuple]:
        since = self._since(days)
        sql = ("SELECT g.id, g.name, SUM(s.seconds) AS t FROM sessions s JOIN games g ON g.id=s.game_id "
               "WHERE g.hidden=0")
        params = []
        if since:
            sql += " AND s.started_at >= ?"
            params.append(since)
        sql += " GROUP BY g.id HAVING t > 0 ORDER BY t DESC LIMIT ?"
        params.append(limit)
        with self.connect() as c:
            return [(r["id"], r["name"], int(r["t"])) for r in c.execute(sql, params)]

    def recent_games(self, limit: int = 8) -> List[Game]:
        sql = (self._SELECT + "WHERE g.hidden=0 GROUP BY g.id HAVING last_played IS NOT NULL "
               "ORDER BY last_played DESC LIMIT ?")
        with self.connect() as c:
            return [Game.from_row(r) for r in c.execute(sql, (limit,))]

    def achievement_facts(self) -> dict:
        real = f"started_at != '{IMPORT_TS}'"
        with self.connect() as c:
            row = c.execute(
                f"SELECT COUNT(*) AS n, COALESCE(MAX(seconds),0) AS longest, "
                f"COUNT(DISTINCT date(started_at)) AS days FROM sessions WHERE {real}").fetchone()
            total = c.execute("SELECT COALESCE(SUM(seconds),0) FROM sessions").fetchone()[0]
            night = c.execute(
                f"SELECT COUNT(*) FROM sessions WHERE {real} "
                "AND CAST(strftime('%H', started_at) AS INTEGER) < 5").fetchone()[0]
            games = c.execute("SELECT COUNT(*) FROM games WHERE hidden=0").fetchone()[0]
            plats = c.execute("SELECT COUNT(DISTINCT platform) FROM games WHERE hidden=0").fetchone()[0]
        return {"sessions": row["n"], "total": int(total), "longest": int(row["longest"]),
                "days": row["days"], "night": night, "games": games, "platforms": plats}

    def set_imported_seconds(self, game_id: int, seconds: int) -> None:
        """Guarda las horas históricas (p. ej. de Steam) como una sesión sintética idempotente."""
        with self.connect() as c:
            c.execute("DELETE FROM sessions WHERE game_id=? AND started_at=?", (game_id, IMPORT_TS))
            if seconds > 0:
                c.execute("INSERT INTO sessions(game_id, started_at, ended_at, seconds) VALUES(?,?,?,?)",
                          (game_id, IMPORT_TS, IMPORT_TS, int(seconds)))

    def real_seconds(self, game_id: int) -> int:
        with self.connect() as c:
            return int(c.execute("SELECT COALESCE(SUM(seconds),0) FROM sessions WHERE game_id=? AND started_at != ?",
                                 (game_id, IMPORT_TS)).fetchone()[0])

    def find_game(self, platform: str = None, external_id: str = "", name: str = "") -> Optional[Game]:
        for g in self.list_games():
            if external_id and g.external_id == external_id and (platform is None or g.platform == platform):
                return g
        if name:
            n = normalize(name)
            for g in self.list_games():
                if normalize(g.name) == n:
                    return g
        return None

    def game_seconds(self, game_id: int, since: Optional[str] = None) -> int:
        sql, params = "SELECT COALESCE(SUM(seconds),0) FROM sessions WHERE game_id=?", [game_id]
        if since:
            sql += " AND started_at >= ?"
            params.append(since)
        with self.connect() as c:
            return int(c.execute(sql, params).fetchone()[0])

    def today_start(self) -> str:
        return datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).isoformat(timespec="seconds")

    # ----------------------------------------------------------- colecciones
    def create_collection(self, name: str) -> int:
        name = (name or "").strip()[:40]
        if not name:
            raise ValueError("La colección necesita un nombre.")
        with self.connect() as c:
            if c.execute("SELECT 1 FROM collections WHERE name=?", (name,)).fetchone():
                raise ValueError(f"Ya existe una colección llamada «{name}».")
            return int(c.execute("INSERT INTO collections(name, created_at) VALUES(?,?)", (name, _now())).lastrowid)

    def rename_collection(self, cid: int, name: str) -> None:
        name = (name or "").strip()[:40]
        if not name:
            raise ValueError("La colección necesita un nombre.")
        with self.connect() as c:
            if c.execute("SELECT 1 FROM collections WHERE name=? AND id!=?", (name, cid)).fetchone():
                raise ValueError(f"Ya existe una colección llamada «{name}».")
            c.execute("UPDATE collections SET name=? WHERE id=?", (name, cid))

    def delete_collection(self, cid: int) -> None:
        with self.connect() as c:
            c.execute("DELETE FROM collections WHERE id=?", (cid,))

    def list_collections(self) -> List[tuple]:
        """[(id, nombre, nº de juegos)]"""
        with self.connect() as c:
            return [(r["id"], r["name"], r["n"]) for r in c.execute(
                "SELECT c.id, c.name, COUNT(g.id) AS n FROM collections c "
                "LEFT JOIN collection_games cg ON cg.collection_id = c.id "
                "LEFT JOIN games g ON g.id = cg.game_id AND g.hidden = 0 "
                "GROUP BY c.id ORDER BY c.name COLLATE NOCASE")]

    def set_in_collection(self, cid: int, game_id: int, present: bool) -> None:
        with self.connect() as c:
            if present:
                c.execute("INSERT OR IGNORE INTO collection_games(collection_id, game_id) VALUES(?,?)", (cid, game_id))
            else:
                c.execute("DELETE FROM collection_games WHERE collection_id=? AND game_id=?", (cid, game_id))

    def collections_of_game(self, game_id: int) -> set:
        with self.connect() as c:
            return {r[0] for r in c.execute("SELECT collection_id FROM collection_games WHERE game_id=?", (game_id,))}

    # ------------------------------------------------- logros, contadores, actividad
    def get_counter(self, key: str) -> int:
        with self.connect() as c:
            r = c.execute("SELECT value FROM counters WHERE key=?", (key,)).fetchone()
        return int(r[0]) if r else 0

    def all_counters(self) -> dict:
        with self.connect() as c:
            return {r["key"]: int(r["value"]) for r in c.execute("SELECT key, value FROM counters")}

    def bump_counter(self, key: str, n: int = 1) -> int:
        with self.connect() as c:
            c.execute("INSERT INTO counters(key, value) VALUES(?, ?) "
                      "ON CONFLICT(key) DO UPDATE SET value = value + ?", (key, n, n))
            return int(c.execute("SELECT value FROM counters WHERE key=?", (key,)).fetchone()[0])

    def unlocked_achievements(self) -> dict:
        with self.connect() as c:
            return {r["key"]: r["unlocked_at"] for r in c.execute("SELECT key, unlocked_at FROM achievements")}

    def unlock_achievement(self, key: str) -> bool:
        with self.connect() as c:
            return c.execute("INSERT OR IGNORE INTO achievements(key, unlocked_at) VALUES(?,?)",
                             (key, _now())).rowcount > 0

    def completed_challenges(self) -> set:
        with self.connect() as c:
            return {(r["key"], r["period"]) for r in c.execute("SELECT key, period FROM challenges")}

    def complete_challenge(self, key: str, period: str) -> bool:
        with self.connect() as c:
            return c.execute("INSERT OR IGNORE INTO challenges(key, period, completed_at) VALUES(?,?,?)",
                             (key, period, _now())).rowcount > 0

    def log_activity(self, kind: str, text: str, xp: int = 0, ref: str = "") -> None:
        with self.connect() as c:
            c.execute("INSERT INTO activity(kind, text, xp, ref, created_at) VALUES(?,?,?,?,?)",
                      (kind, text[:200], int(xp), str(ref), _now()))
            c.execute("DELETE FROM activity WHERE id NOT IN (SELECT id FROM activity ORDER BY id DESC LIMIT 500)")

    def recent_activity(self, limit: int = 30) -> List[dict]:
        with self.connect() as c:
            return [dict(r) for r in c.execute(
                "SELECT kind, text, xp, ref, created_at FROM activity ORDER BY id DESC LIMIT ?", (limit,))]

    def activity_since(self, kind: str, since: str) -> List[dict]:
        with self.connect() as c:
            return [dict(r) for r in c.execute(
                "SELECT text, ref, created_at FROM activity WHERE kind=? AND created_at >= ?", (kind, since))]

    def xp_from_rewards(self) -> int:
        with self.connect() as c:
            return int(c.execute("SELECT COALESCE(SUM(xp),0) FROM activity WHERE kind IN ('achievement','challenge')")
                       .fetchone()[0])

    def distinct_play_days(self, since: str) -> int:
        with self.connect() as c:
            return int(c.execute(
                "SELECT COUNT(DISTINCT date(started_at)) FROM sessions WHERE started_at >= ? AND started_at != ?",
                (since, IMPORT_TS)).fetchone()[0])

    # ----------------------------------------------------------- memoria de la IA
    def add_memory(self, text: str, limit: int = 30) -> int:
        text = (text or "").strip()[:300]
        if not text:
            raise ValueError("No hay nada que recordar.")
        with self.connect() as c:
            mid = int(c.execute("INSERT INTO ai_memory(text, created_at) VALUES(?,?)", (text, _now())).lastrowid)
            c.execute("DELETE FROM ai_memory WHERE id NOT IN (SELECT id FROM ai_memory ORDER BY id DESC LIMIT ?)",
                      (limit,))
        return mid

    def list_memory(self) -> List[dict]:
        with self.connect() as c:
            return [dict(r) for r in c.execute("SELECT id, text, created_at FROM ai_memory ORDER BY id")]

    def delete_memory(self, memory_id: Optional[int] = None) -> int:
        with self.connect() as c:
            if memory_id is None:
                return c.execute("DELETE FROM ai_memory").rowcount
            return c.execute("DELETE FROM ai_memory WHERE id=?", (memory_id,)).rowcount

    # ------------------------------------------------------------------ chat
    def add_chat(self, role: str, content: str) -> None:
        with self.connect() as c:
            c.execute("INSERT INTO chat_history(role, content, created_at) VALUES(?,?,?)",
                      (role, content, _now()))

    def get_chat(self, limit: int = 20) -> List[dict]:
        with self.connect() as c:
            rows = c.execute(
                "SELECT role, content FROM chat_history ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    def clear_chat(self) -> None:
        with self.connect() as c:
            c.execute("DELETE FROM chat_history")


def init_db(db: DatabaseManager) -> DatabaseManager:
    db.init()
    return db
