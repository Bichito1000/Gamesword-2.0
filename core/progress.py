"""Perfil, nivel, experiencia, logros y desafíos de Gamesword (todo local, calculado con datos reales)."""
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, List, Optional

from utils.logger import get_logger

log = get_logger("progress")

XP_PER_HOUR = 10


@dataclass
class Unlock:
    kind: str          # "achievement" | "challenge"
    key: str
    name: str
    xp: int


def xp_for_level(level: int) -> int:
    """XP acumulada necesaria para ALCANZAR ese nivel: 1→0, 2→100, 3→300, 4→600…"""
    return 50 * level * (level - 1)


def level_for(xp: int) -> int:
    level = 1
    while xp >= xp_for_level(level + 1):
        level += 1
    return level


def _c(facts, key):
    return facts["counters"].get(key, 0)


# (clave, icono, nombre, descripción, XP, regla)
ACHIEVEMENTS = [
    ("first_session", "🎮", "Primer paso", "Completa tu primera sesión", 50, lambda f: f["sessions"] >= 1),
    ("h10", "⏱", "10 horas", "Suma 10 h de juego", 100, lambda f: f["total"] >= 10 * 3600),
    ("h50", "🔥", "50 horas", "Suma 50 h de juego", 200, lambda f: f["total"] >= 50 * 3600),
    ("h100", "💯", "100 horas", "Suma 100 h de juego", 400, lambda f: f["total"] >= 100 * 3600),
    ("h500", "👑", "500 horas", "Suma 500 h de juego", 1000, lambda f: f["total"] >= 500 * 3600),
    ("marathon", "🏃", "Maratón", "Una sesión de 3 h o más", 150, lambda f: f["longest"] >= 3 * 3600),
    ("steady", "📅", "Constante", "Juega en 7 días distintos", 150, lambda f: f["days"] >= 7),
    ("night_owl", "🌙", "Noctámbulo", "Empieza a jugar entre 00:00 y 05:00", 75, lambda f: f["night"] >= 1),
    ("games10", "📚", "Coleccionista", "10 juegos en la biblioteca", 100, lambda f: f["games"] >= 10),
    ("games50", "🏛", "Gran biblioteca", "50 juegos en la biblioteca", 300, lambda f: f["games"] >= 50),
    ("multi", "🌐", "Multiplataforma", "Juegos de 3 plataformas distintas", 150, lambda f: f["platforms"] >= 3),
    # --- por usar Gamesword
    ("launch1", "🚀", "Despegue", "Abre un juego desde Gamesword", 25, lambda f: _c(f, "launches") >= 1),
    ("launch10", "⚡", "Lanzador habitual", "Abre 10 juegos desde Gamesword", 100, lambda f: _c(f, "launches") >= 10),
    ("first_ai", "🤖", "Primera conversación", "Habla con Gamesword AI", 25, lambda f: _c(f, "ai_messages") >= 1),
    ("ai25", "🧠", "Copiloto", "Envía 25 mensajes a Gamesword AI", 100, lambda f: _c(f, "ai_messages") >= 25),
    ("synced", "🔄", "Todo en un sitio", "Sincroniza tus bibliotecas", 50, lambda f: _c(f, "syncs") >= 1),
    ("collection", "🗂", "Organizado", "Crea una colección", 50, lambda f: _c(f, "collections_created") >= 1),
    ("customizer", "🎨", "A tu estilo", "Personaliza el tema o los colores", 50, lambda f: _c(f, "customizations") >= 1),
    ("safe", "🛡", "Previsor", "Crea una copia de seguridad", 50, lambda f: _c(f, "backups") >= 1),
    ("social", "👥", "Sociable", "Añade a un amigo", 50, lambda f: _c(f, "friends_added") >= 1),
]
ACH_BY_KEY = {a[0]: a for a in ACHIEVEMENTS}


def _day_start(now: datetime) -> str:
    return now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat(timespec="seconds")


def _week_start(now: datetime) -> str:
    return _day_start(now - timedelta(days=now.weekday()))


def period_key(period: str, now: datetime) -> str:
    if period == "day":
        return now.date().isoformat()
    iso = now.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


# (clave, nombre, descripción, periodo, XP, unidad, función(db, now) -> (valor, objetivo))
def _play_today(db, now):
    return db.total_seconds(since=_day_start(now)) // 60, 30


def _launch_today(db, now):
    return len(db.activity_since("launch", _day_start(now))), 2


def _week_hours(db, now):
    return round(db.total_seconds(since=_week_start(now)) / 3600, 1), 5


def _week_days(db, now):
    return db.distinct_play_days(_week_start(now)), 3


def _week_games(db, now):
    return len({a["ref"] for a in db.activity_since("launch", _week_start(now)) if a["ref"]}), 3


CHALLENGES = [
    ("day_play30", "Calentamiento", "Juega 30 minutos hoy", "day", 30, "min", _play_today),
    ("day_launch2", "Doble partida", "Abre 2 juegos hoy desde Gamesword", "day", 30, "juegos", _launch_today),
    ("week_5h", "Semana intensa", "Juega 5 horas esta semana", "week", 150, "h", _week_hours),
    ("week_3days", "Constancia semanal", "Juega en 3 días distintos esta semana", "week", 100, "días", _week_days),
    ("week_3games", "Explorador", "Abre 3 juegos distintos esta semana", "week", 100, "juegos", _week_games),
]


class ProgressManager:
    def __init__(self, db, settings):
        self.db, self.settings = db, settings
        self.on_unlock: Optional[Callable[[List[Unlock]], None]] = None

    # ------------------------------------------------------------------ eventos
    def record(self, counter: str, n: int = 1) -> List[Unlock]:
        self.db.bump_counter(counter, n)
        return self.evaluate()

    def log_activity(self, kind: str, text: str, xp: int = 0, ref: str = "") -> None:
        self.db.log_activity(kind, text, xp, ref)

    def _facts(self) -> dict:
        facts = self.db.achievement_facts()
        facts["counters"] = self.db.all_counters()
        return facts

    def evaluate(self, now: Optional[datetime] = None) -> List[Unlock]:
        now = now or datetime.now()
        facts, unlocked, done = self._facts(), self.db.unlocked_achievements(), self.db.completed_challenges()
        new: List[Unlock] = []
        for key, _icon, name, _desc, xp, rule in ACHIEVEMENTS:
            if key not in unlocked and rule(facts) and self.db.unlock_achievement(key):
                self.db.log_activity("achievement", f"Logro desbloqueado: {name}", xp, key)
                new.append(Unlock("achievement", key, name, xp))
        for key, name, _desc, period, xp, _unit, fn in CHALLENGES:
            pkey = period_key(period, now)
            if (key, pkey) in done:
                continue
            value, target = fn(self.db, now)
            if value >= target and self.db.complete_challenge(key, pkey):
                self.db.log_activity("challenge", f"Desafío completado: {name}", xp, f"{key}:{pkey}")
                new.append(Unlock("challenge", key, name, xp))
        if new and self.on_unlock:
            try:
                self.on_unlock(new)
            except Exception:  # noqa: BLE001
                log.exception("Error notificando logros")
        return new

    # ----------------------------------------------------------------- consulta
    def xp_total(self) -> int:
        hours = self.db.total_seconds() / 3600
        return int(hours * XP_PER_HOUR) + self.db.xp_from_rewards()

    def snapshot(self, now: Optional[datetime] = None) -> dict:
        now = now or datetime.now()
        xp = self.xp_total()
        level = level_for(xp)
        base, nxt = xp_for_level(level), xp_for_level(level + 1)
        unlocked = self.db.unlocked_achievements()
        done = self.db.completed_challenges()
        achievements = [{"key": k, "icon": i, "name": n, "desc": d, "xp": x, "unlocked_at": unlocked.get(k)}
                        for k, i, n, d, x, _ in ACHIEVEMENTS]
        challenges = []
        for key, name, desc, period, xp_r, unit, fn in CHALLENGES:
            value, target = fn(self.db, now)
            challenges.append({"key": key, "name": name, "desc": desc, "period": period, "xp": xp_r, "unit": unit,
                               "value": value, "target": target,
                               "done": (key, period_key(period, now)) in done})
        return {"xp": xp, "level": level, "xp_in_level": xp - base, "xp_to_next": nxt - base,
                "achievements": achievements, "challenges": challenges,
                "unlocked": sum(1 for a in achievements if a["unlocked_at"]),
                "playtime": self.db.total_seconds(), "activity": self.db.recent_activity(40),
                "top_games": self.db.top_games(3)}
