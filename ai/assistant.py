"""Gamesword AI: comandos locales (funcionan sin internet) + chat con un modelo compatible con OpenAI."""
import json
import os
import re
import time
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import List, Optional, Tuple

import requests

from core import system_monitor
from utils.helpers import format_duration, normalize
from utils.logger import get_logger
from .recommendations import (by_tags, find_in_catalog, for_user, similar_to, tags_from_text)

log = get_logger("assistant")

ACTION_RE = re.compile(r"\[\[\s*ABRIR\s*:\s*(.+?)\s*\]\]", re.I)

_FILLER = (r"(?:(?:oye|hey|ok|vale|venga|y|gamesword|por favor|puedes|podrias|me puedes|me podrias|"
           r"quiero que|necesito que|me|nos)\s+)*")
OPEN_RE = re.compile(
    r"^" + _FILLER +
    r"(?:abre|abreme|abres|abrir|abrirme|lanza|lanzame|lanzas|lanzar|inicia|iniciame|inicias|iniciar|"
    r"ejecuta|ejecutame|ejecutar|arranca|arrancame|arrancar|enciende|encendeme|pon|ponme|poner|pones|saca|"
    r"juega a|jugar a|jugar al|juguemos a|jugamos a|vamos a jugar a|vamos a jugar al|quiero jugar a|quiero jugar al|"
    r"quiero echar una partida a|echa una partida a|echame una partida a|quiero jugar|vamos a jugar)"
    r"\s+(?:a\s+|al\s+|la\s+|el\s+|una partida de\s+)?(?P<rest>.+)$")
CLOSE_RE = re.compile(r"^" + _FILLER + r"(?:cierra|cierrame|cierras|cerrar|termina|mata)\s+(?P<rest>.+)$")
REMOVE_RE = re.compile(r"^" + _FILLER + r"(?:quita|quitame|elimina|borra|saca)\s+(?P<rest>.+?)\s+de\s+(?:mi\s+)?(?:la\s+)?biblioteca$")
REMEMBER_RE = re.compile(r"^" + _FILLER + r"(?:recuerda|apunta|anota|acuerdate de|memoriza)\s+(?:que\s+)?(?P<fact>.+)$")
RECALL_RE = re.compile(r"\b(?:que recuerdas|que sabes de mi|que has memorizado|tu memoria|mi memoria)\b")
FORGET_ALL_RE = re.compile(r"^" + _FILLER + r"(?:olvida todo|borra tu memoria|borra la memoria|olvidalo todo)$")
FORGET_RE = re.compile(r"^" + _FILLER + r"(?:olvida|olvidate de)\s+(?:que\s+)?(?P<fact>.+)$")
SPLIT_RE = re.compile(
    r"\s+(?:y\s+(?:luego|despues|a continuacion|tambien)|y|luego|despues|a continuacion|seguido de|ademas)\s+")
LIST_RE = re.compile(
    r"\b(?:(?:que|cuales|mis|lista|muestrame|ensename|dime)\b.*\bjuegos\b.*\b(?:tengo|instalad\w*|biblioteca)\b"
    r"|mi biblioteca|juegos instalados|cuantos juegos)")
STATS_RE = re.compile(
    r"\b(?:(?:horas|tiempo|minutos|cuanto|cuantas)\b.*\b(?:jugad\w*|jugue|juego|jugando|jugar)\b|estadisticas?)")
LAUNCHERS_RE = re.compile(r"\b(?:que|cuales)\b.*\b(?:lanzadores|plataformas|launchers)\b")
HELP_RE = re.compile(r"\bayuda\b|que (?:puedes|sabes) hacer|como funcionas|que haces")
SYSTEM_RE = re.compile(
    r"\b(rendimiento|cpu|ram|memoria ram|gpu|grafica|temperatura|como va mi pc|como esta funcionando mi|"
    r"como funciona mi (?:pc|ordenador)|estado del (?:pc|sistema|ordenador)|diagnostic\w*|va lent\w*|va muy lent\w*|"
    r"tirones|lag|espacio en disco|disco)\b")
DIAG_RE = re.compile(r"diagnostic|va lent|va muy lent|tirones|\blag\b|disco|problema|como esta funcionando")
RECO_RE = re.compile(
    r"parecid|similar|recomiend|recomend|sugier|sugerenc|busca(?:me)? juegos|juegos (?:cooperativ|coop|de |para )"
    r"|algo (?:para|de) jugar|que jugar|a que jugar|descubr|quiero jugar a algo")

PROVIDER_ERRORS = {
    401: "La clave API no es válida o ha caducado. Revísala en Ajustes → Inteligencia artificial.",
    403: "El proveedor ha rechazado la petición (permisos o región). Revisa tu cuenta.",
    404: "No se encontró el modelo o la dirección del servidor. Revisa Ajustes → Inteligencia artificial.",
    429: "Se ha superado el límite de uso del proveedor de IA. Espera un poco o revisa tu plan.",
}


@dataclass
class PendingAction:
    """Acción importante que solo se ejecuta si el usuario la confirma."""
    kind: str                     # close_game | remove_game | clear_memory
    prompt: str
    payload: dict = field(default_factory=dict)
    created: float = field(default_factory=time.time)


@dataclass
class AssistantReply:
    text: str
    launched: List[str] = field(default_factory=list)
    used_llm: bool = False
    pending: Optional[PendingAction] = None


def _score(q: str, n: str) -> float:
    if not q or not n:
        return 0.0
    if q == n:
        return 1.0
    qt, nt = q.split(), n.split()
    if set(qt) <= set(nt):
        return 0.92
    if set(nt) <= set(qt) and len(nt) >= 1 and len(n) > 3:
        return 0.9
    return SequenceMatcher(None, q, n).ratio()


def _clean_target(text: str) -> str:
    t = normalize(text)
    t = re.sub(r"\b(por favor|ahora|ya|en mi pc|en el ordenador)\b", " ", t)
    t = re.sub(r"^(?:el juego |la aplicacion |la app |el |la |los |las |mi |juego )+", "", t.strip())
    return t.strip()


class GamesAssistant:
    def __init__(self, db, settings, tracker, platforms):
        self.db, self.settings, self.tracker, self.platforms = db, settings, tracker, platforms
        self.license = None      # LicenseManager (opcional)
        self.progress = None     # ProgressManager (opcional)
        self._pending: Optional[PendingAction] = None
        self._tool_pending: Optional[PendingAction] = None

    # ---------------------------------------------------------------- API
    def respond(self, text: str, on_token=None) -> AssistantReply:
        text = (text or "").strip()
        if not text:
            return AssistantReply("Dime qué necesitas: abrir un juego, ver tus horas, recomendaciones…")
        history = self.db.get_chat(12)
        self.db.add_chat("user", text)
        reply = self._local(text)
        if reply is None:
            reply = self._llm(text, history, on_token)
        if reply.pending:
            self._pending = reply.pending
        self.db.add_chat("assistant", reply.text)
        if self.progress is not None:
            try:
                self.progress.record("ai_messages")
            except Exception:  # noqa: BLE001
                log.exception("No se pudo registrar el progreso")
        return reply

    @property
    def has_llm(self) -> bool:
        return self._api_key() is not None or self._is_local_url()

    # ---------------------------------------------------------- resolución
    def resolve(self, name: str) -> Tuple[Optional[tuple], List[str]]:
        """Devuelve (('game', Game) | ('launcher', key), sugerencias)."""
        q = _clean_target(name)
        games = self.db.list_games()
        scored = sorted(((_score(q, normalize(g.name)), g) for g in games), key=lambda x: -x[0])
        if scored and scored[0][0] >= 0.95:
            return ("game", scored[0][1]), []
        key = self.platforms.resolve_alias(q)
        if key:
            return ("launcher", key), []
        if scored and scored[0][0] >= 0.62:
            return ("game", scored[0][1]), []
        return None, [g.name for s, g in scored[:3] if s >= 0.4]

    def _launch(self, target: tuple) -> Tuple[bool, str]:
        kind, obj = target
        if kind == "game":
            return self.tracker.play(obj)
        return self.platforms.open(obj)

    def _target_label(self, target: tuple) -> str:
        from core.platform_manager import LAUNCHERS_BY_KEY
        return target[1].name if target[0] == "game" else LAUNCHERS_BY_KEY[target[1]].name

    # ----------------------------------------------------- comandos locales
    def _local(self, text: str) -> Optional[AssistantReply]:
        t = normalize(text.replace(",", " y "))
        custom = self._custom(t)
        if custom:
            return custom
        for rx, fn in ((REMEMBER_RE, self._remember), (FORGET_ALL_RE, self._forget_all), (FORGET_RE, self._forget)):
            m = rx.match(t)
            if m:
                return fn(m.groupdict().get("fact", ""))
        if RECALL_RE.search(t):
            return self._recall()
        m = REMOVE_RE.match(t)
        if m:
            return self._ask_remove(m.group("rest"))
        m = CLOSE_RE.match(t)
        if m:
            return self._ask_close(m.group("rest"))
        if LIST_RE.search(t):
            return self._list_games("instalad" in t)
        if STATS_RE.search(t):
            return self._stats(t)
        if LAUNCHERS_RE.search(t):
            return self._list_launchers()
        if HELP_RE.search(t):
            return self._help()
        if SYSTEM_RE.search(t) and not OPEN_RE.match(t):
            if DIAG_RE.search(t):
                return AssistantReply(system_monitor.diagnose())
            return AssistantReply(system_monitor.describe(system_monitor.snapshot()))
        if RECO_RE.search(t):
            return self._recommend(text, t)
        m = OPEN_RE.match(t)
        if m:
            return self._open(m.group("rest"))
        return None

    # ---------------------------------------------- comandos personalizados
    def _custom(self, t: str) -> Optional[AssistantReply]:
        for cmd in self.settings.get("ai.custom_commands", []) or []:
            phrase = normalize(str(cmd.get("phrase", "")))
            names = [n for n in cmd.get("targets", []) if str(n).strip()]
            if phrase and names and (t == phrase or phrase in t or SequenceMatcher(None, t, phrase).ratio() >= 0.88):
                targets, missing = [], []
                for name in names:
                    tg, sug = self.resolve(str(name))
                    (targets.append(tg) if tg else missing.append((str(name), sug)))
                reply = self._run_targets(targets, missing)
                reply.text = f"Comando «{cmd.get('phrase')}»:\n" + reply.text
                return reply
        return None

    # ------------------------------------------------------------- memoria
    def _memory_on(self) -> bool:
        return bool(self.settings.get("ai.memory_enabled", True))

    def _remember(self, fact: str) -> AssistantReply:
        if not self._memory_on():
            return AssistantReply("La memoria está desactivada en Ajustes → Inteligencia artificial.")
        try:
            self.db.add_memory(fact, int(self.settings.get("ai.memory_limit", 30)))
        except ValueError as exc:
            return AssistantReply(str(exc))
        return AssistantReply(f"Anotado: «{fact.strip()}». Puedes ver o borrar mi memoria en Ajustes.")

    def _recall(self) -> AssistantReply:
        items = self.db.list_memory()
        if not self._memory_on():
            return AssistantReply("La memoria está desactivada, así que no estoy guardando nada nuevo.")
        if not items:
            return AssistantReply("Todavía no me has pedido que recuerde nada. Prueba con «recuerda que…».")
        return AssistantReply("Esto es lo que recuerdo:\n" + "\n".join(f"• {m['text']}" for m in items))

    def _forget(self, fact: str) -> AssistantReply:
        words = [w for w in normalize(fact).split() if len(w) > 2]
        removed = 0
        for m in self.db.list_memory():
            if words and all(w in normalize(m["text"]) for w in words):
                removed += self.db.delete_memory(m["id"])
        return AssistantReply(f"He olvidado {removed} cosa(s)." if removed else "No encuentro nada así en mi memoria.")

    def _forget_all(self, _fact: str = "") -> AssistantReply:
        n = len(self.db.list_memory())
        if not n:
            return AssistantReply("Mi memoria ya está vacía.")
        return AssistantReply(f"Tengo {n} cosas anotadas.", pending=PendingAction(
            "clear_memory", f"¿Borrar toda mi memoria ({n} notas)?"))

    # ------------------------------------------------ acciones con confirmación
    def _active_games(self) -> list:
        games = []
        for gid in self.tracker.active():
            g = self.db.get_game(gid)
            if g:
                games.append(g)
        return games

    def _ask_close(self, rest: str) -> AssistantReply:
        rn = normalize(rest)
        active = self._active_games()
        generic = (not rn) or any(w in rn.split() for w in ("juego", "esto", "esta", "partida", "abierto"))
        if generic:
            if not active:
                return AssistantReply("No hay ningún juego en marcha que yo haya iniciado y esté midiendo. Si lo abriste "
                                      "por fuera de Gamesword no puedo cerrarlo desde aquí.")
            if len(active) > 1:
                names = ", ".join(g.name for g in active)
                return AssistantReply(f"Hay varios juegos abiertos ({names}). Dime cuál quieres cerrar.")
            target = active[0]
        else:
            tg, _ = self.resolve(rest)
            if not tg or tg[0] != "game":
                return AssistantReply(f"No encuentro «{rest.strip()}» en tu biblioteca.")
            target = tg[1]
            if target.id not in [g.id for g in active]:
                return AssistantReply(f"{target.name} no aparece como abierto desde Gamesword.")
        return AssistantReply(f"Voy a cerrar {target.name}.", pending=PendingAction(
            "close_game", f"¿Cerrar {target.name}? Perderás el progreso sin guardar.",
            {"game_id": target.id, "name": target.name}))

    def _ask_remove(self, rest: str) -> AssistantReply:
        tg, _ = self.resolve(rest)
        if not tg or tg[0] != "game":
            return AssistantReply(f"No encuentro «{rest.strip()}» en tu biblioteca.")
        g = tg[1]
        return AssistantReply(f"Voy a quitar {g.name} de la biblioteca.", pending=PendingAction(
            "remove_game", f"¿Quitar «{g.name}» de tu biblioteca? (No se borra nada de tu disco.)",
            {"game_id": g.id, "name": g.name}))

    def execute_pending(self, confirm: bool) -> AssistantReply:
        """Llamado por la interfaz cuando el usuario pulsa Sí o Cancelar."""
        pending, self._pending = self._pending, None
        if pending is None:
            return AssistantReply("No tengo ninguna acción pendiente de confirmar.")
        if time.time() - pending.created > 180:
            return AssistantReply("Esa confirmación caducó. Vuelve a pedírmelo si todavía lo quieres.")
        if not confirm:
            return AssistantReply("De acuerdo, no hago nada.")
        try:
            if pending.kind == "close_game":
                n = self.tracker.close_game(pending.payload["game_id"])
                if n:
                    return AssistantReply(f"He pedido a {pending.payload['name']} que se cierre ({n} proceso(s)). "
                                          "Si no responde, ciérralo desde el propio juego.")
                return AssistantReply(f"{pending.payload['name']} ya no parecía estar en marcha.")
            if pending.kind == "remove_game":
                self.db.delete_game(pending.payload["game_id"])
                return AssistantReply(f"He quitado {pending.payload['name']} de tu biblioteca.")
            if pending.kind == "clear_memory":
                return AssistantReply(f"Memoria borrada ({self.db.delete_memory()} notas).")
        except Exception as exc:  # noqa: BLE001
            log.exception("Error ejecutando acción confirmada")
            return AssistantReply(f"No se pudo completar la acción: {exc}")
        return AssistantReply("Acción desconocida.")

    def _open(self, rest: str) -> AssistantReply:
        targets: List[tuple] = []
        missing: List[Tuple[str, List[str]]] = []
        parts = [p for p in SPLIT_RE.split(rest) if p.strip()]
        resolved = [(p, *self.resolve(p)) for p in parts] if len(parts) > 1 else []
        if resolved and any(tg for _, tg, _ in resolved):
            seen = set()                                       # "abre Discord y después Rocket League"
            for p, tg, sug in resolved:
                if not tg:
                    missing.append((p, sug))
                    continue
                ident = (tg[0], getattr(tg[1], "id", tg[1]))
                if ident not in seen:
                    seen.add(ident)
                    targets.append(tg)
        else:
            whole, suggestions = self.resolve(rest)
            if whole:
                targets = [whole]
            else:
                missing = [(rest, suggestions)]
        return self._run_targets(targets, missing)

    def _run_targets(self, targets: List[tuple], missing: List[Tuple[str, List[str]]]) -> AssistantReply:
        lines, launched = [], []
        for i, tg in enumerate(targets):
            if i:
                time.sleep(2.5)      # dar tiempo a que arranque el primero (p. ej. Discord → juego)
            ok, msg = self._launch(tg)
            lines.append(("✅ " if ok else "⚠️ ") + msg)
            if ok:
                launched.append(self._target_label(tg))
        for name, sug in missing:
            hint = f" ¿Quizá {', '.join('«' + s + '»' for s in sug)}?" if sug else ""
            lines.append(f"❓ No encuentro «{name.strip()}» en tu biblioteca.{hint} "
                         "Puedes añadirlo en Biblioteca → Añadir juego o con Escanear juegos.")
        return AssistantReply("\n".join(lines), launched)

    def _list_games(self, installed_only: bool = False) -> AssistantReply:
        games = self.db.list_games(order="played", installed=True if installed_only else None)
        if not games:
            return AssistantReply("Tu biblioteca está vacía. Ve a **Biblioteca → Sincronizar bibliotecas** para importar "
                                  "tus juegos de Steam, Epic, Ubisoft, GOG y EA, o añade uno manualmente.")
        total_all = self.db.count_games()
        kind = "instalados" if installed_only else "en tu biblioteca"
        lines = [f"Tienes **{len(games)} juegos** {kind}"
                 + ("" if installed_only else f" ({self.db.count_installed()} instalados)") + ". Los más jugados:"]
        for g in games[:12]:
            lines.append(f"• {g.name} ({g.platform.title()}) — {format_duration(g.total_seconds)}"
                         + ("" if g.installed else " · sin instalar"))
        if len(games) > 12:
            lines.append(f"…y {len(games) - 12} más.")
        return AssistantReply("\n".join(lines))

    def _list_launchers(self) -> AssistantReply:
        from core.platform_manager import LAUNCHERS_BY_KEY
        keys = self.platforms.installed_keys()
        if not keys:
            return AssistantReply("No he encontrado ningún lanzador instalado. Revisa la pestaña Lanzadores.")
        return AssistantReply("Lanzadores detectados: " + ", ".join(LAUNCHERS_BY_KEY[k].name for k in keys) + ".")

    def _stats(self, t: str) -> AssistantReply:
        if "hoy" in t:
            period = "today"
        elif re.search(r"\bmes\b", t):
            period = "month"
        elif re.search(r"\b(total|siempre|historial|en total)\b", t):
            period = "total"
        else:
            period = "week"
        game = ""
        for g in self.db.list_games():
            n = normalize(g.name)
            if len(n) > 3 and n in t:
                game = g.name
                break
        return AssistantReply(self._playtime_text(period, game))

    def _playtime_text(self, period: str = "week", game: str = "") -> str:
        since, label, days = {
            "today": (self.db.today_start(), "hoy", 1),
            "month": (self.db._since(30), "en los últimos 30 días", 30),
            "total": (None, "en total", None),
        }.get(period, (self.db.week_start(), "esta semana", None))
        if game:
            g = next((x for x in self.db.list_games() if normalize(x.name) == normalize(game)), None)
            if g is None:
                return f"No encuentro «{game}» en tu biblioteca."
            return f"Has jugado a **{g.name}** {format_duration(self.db.game_seconds(g.id, since))} {label}."
        total = self.db.total_seconds(since=since)
        if total == 0:
            return (f"Todavía no tengo tiempo registrado {label}. Juega a algo desde Gamesword "
                    "y lo iré contando.")
        text = f"Has jugado **{format_duration(total)}** {label}."
        top = self.db.top_games(3, days=days) if days else (self.db.top_games(3) if since is None else [])
        if top:
            text += " Lo más jugado: " + ", ".join(f"{n} ({format_duration(sec)})" for _, n, sec in top) + "."
        return text

    def _help(self) -> AssistantReply:
        return AssistantReply(
            "Esto es lo que sé hacer:\n"
            "• «Ábreme Fortnite» · «Abre Discord y después Rocket League»\n"
            "• «¿Qué juegos tengo instalados?»\n"
            "• «¿Cuántas horas he jugado esta semana?» (o hoy / este mes / a un juego concreto)\n"
            "• «Quiero jugar a algo parecido a GTA V» · «Juegos cooperativos para jugar con amigos»\n"
            "• Preguntas de configuración, problemas técnicos y trucos (necesita una clave de IA en Ajustes).")

    def _recommend(self, original: str, t: str) -> AssistantReply:
        games = self.db.list_games(order="played")
        owned = [g.name for g in games]
        m = re.search(r"(?:parecid[oa]s?|similar(?:es)?|como)\s+(?:a|al)?\s*(?P<title>.+)$", t)
        if m:
            entry = find_in_catalog(m.group("title"))
            if entry:
                recs = similar_to(entry, 5, owned)
                return AssistantReply(self._format_recs(f"Si te gusta **{entry['name']}**, prueba:", recs))
        tags = tags_from_text(t)
        if tags:
            recs = by_tags(tags, 6, owned)
            if recs:
                return AssistantReply(self._format_recs("Te propongo estos (" + ", ".join(tags) + "):", recs))
        recs = for_user(games, 6)
        return AssistantReply(self._format_recs("Según lo que más juegas, te pueden gustar:", recs))

    @staticmethod
    def _format_recs(title: str, recs: List[dict]) -> str:
        if not recs:
            return "No he encontrado recomendaciones con eso. Prueba con otro género o juego."
        lines = [title]
        for r in recs:
            lines.append(f"• **{r['name']}** ({r['year']}) — {r['reason']}")
        lines.append("Mira la pestaña Descubrir para ver portadas y enlaces a la tienda.")
        return "\n".join(lines)

    # ---------------------------------------------------------------- LLM
    def _api_key(self) -> Optional[str]:
        key = (self.settings.get("ai.api_key", "") or "").strip() or os.environ.get("OPENAI_API_KEY", "").strip()
        return key or None

    def _is_local_url(self) -> bool:
        url = (self.settings.get("ai.base_url", "") or "").lower()
        return "localhost" in url or "127.0.0.1" in url

    TOOLS = [
        {"type": "function", "function": {
            "name": "open_target", "description": "Abre un juego de la biblioteca del usuario o un lanzador "
            "(Steam, Epic, Discord...). Llámala una vez por cada cosa que haya que abrir, en orden.",
            "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}}},
        {"type": "function", "function": {
            "name": "get_playtime", "description": "Tiempo jugado por el usuario.",
            "parameters": {"type": "object", "properties": {
                "period": {"type": "string", "enum": ["today", "week", "month", "total"]},
                "game": {"type": "string", "description": "Nombre del juego (opcional)"}}}}},
        {"type": "function", "function": {
            "name": "list_library", "description": "Lista los juegos de la biblioteca, de más a menos jugado.",
            "parameters": {"type": "object", "properties": {}}}},
        {"type": "function", "function": {
            "name": "recommend_games", "description": "Recomienda juegos que el usuario no tiene.",
            "parameters": {"type": "object", "properties": {
                "similar_to": {"type": "string", "description": "Título de referencia"},
                "query": {"type": "string", "description": "Género o descripción, p. ej. cooperativos de terror"}}}}},
        {"type": "function", "function": {
            "name": "system_status", "description": "Uso actual de CPU, RAM y GPU del PC.",
            "parameters": {"type": "object", "properties": {}}}},
        {"type": "function", "function": {
            "name": "diagnose_pc", "description": "Diagnóstico del PC: avisos de CPU, RAM, GPU y disco.",
            "parameters": {"type": "object", "properties": {}}}},
        {"type": "function", "function": {
            "name": "close_game", "description": "Cierra un juego abierto desde Gamesword. El usuario tendrá que "
            "confirmarlo con un botón; no se cierra nada hasta entonces.",
            "parameters": {"type": "object", "properties": {"name": {"type": "string",
                           "description": "Juego a cerrar; vacío si solo hay uno abierto"}}}}},
        {"type": "function", "function": {
            "name": "remove_game", "description": "Quita un juego de la biblioteca (requiere confirmación del usuario).",
            "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}}},
        {"type": "function", "function": {
            "name": "remember", "description": "Guarda un dato que el usuario pide recordar (gustos, datos de su PC…).",
            "parameters": {"type": "object", "properties": {"fact": {"type": "string"}}, "required": ["fact"]}}},
    ]

    def _system_prompt(self, tools: bool) -> str:
        from core.platform_manager import LAUNCHERS_BY_KEY
        games = self.db.list_games(order="played")
        lib = "; ".join(f"{g.name} ({g.platform}, {format_duration(g.total_seconds)})" for g in games[:40]) or "vacía"
        week = format_duration(self.db.total_seconds(since=self.db.week_start()))
        launchers = ", ".join(LAUNCHERS_BY_KEY[k].name for k in self.platforms.installed_keys()) or "ninguno detectado"
        memory = ""
        if self._memory_on():
            facts = [m["text"] for m in self.db.list_memory()]
            if facts:
                memory = "Cosas que el usuario te pidió recordar: " + "; ".join(facts) + ".\n"
        how = ("Para abrir juegos o lanzadores, consultar horas, listar la biblioteca, recomendar, diagnosticar el PC, "
               "cerrar o quitar juegos y recordar datos usa las herramientas disponibles; no inventes resultados. "
               "Cerrar y quitar juegos requieren confirmación del usuario." if tools else
               "Si el usuario pide abrir un juego o lanzador de su biblioteca, responde brevemente y añade al final "
               "una línea por cada uno con el formato exacto [[ABRIR: nombre]].")
        return (
            "Eres Gamesword AI, el asistente de la aplicación Gamesword para Windows, especializado en "
            "videojuegos. Responde en español, de forma breve y útil (máximo ~150 palabras salvo que pidan más). "
            "Ayudas con recomendaciones, configuración gráfica, rendimiento, problemas técnicos, guías y trucos.\n"
            f"Biblioteca del usuario ({len(games)} juegos): {lib}.\n"
            f"Lanzadores instalados: {launchers}. Tiempo jugado esta semana: {week}.\n{memory}{how} "
            "No inventes juegos que no estén en su biblioteca; si no está, dilo. No pidas contraseñas ni claves.")

    # --- herramientas (tool calling) -------------------------------------
    def _run_tool(self, name: str, args: dict, launched: List[str]) -> str:
        try:
            if name == "open_target":
                target, sug = self.resolve(str(args.get("name", "")))
                if not target:
                    hint = f" Parecidos: {', '.join(sug)}." if sug else ""
                    return f"No existe «{args.get('name')}» en la biblioteca.{hint}"
                ok, msg = self._launch(target)
                if ok:
                    launched.append(self._target_label(target))
                return msg
            if name == "get_playtime":
                return self._playtime_text(args.get("period", "week"), args.get("game", ""))
            if name == "list_library":
                return self._list_games().text
            if name == "recommend_games":
                return self._recommend(args.get("query", "") or "", normalize(
                    (args.get("query") or "") + (" parecido a " + args["similar_to"] if args.get("similar_to") else ""))).text
            if name == "system_status":
                return system_monitor.describe(system_monitor.snapshot())
            if name == "diagnose_pc":
                return system_monitor.diagnose()
            if name in ("close_game", "remove_game"):
                reply = (self._ask_close(args.get("name", "")) if name == "close_game"
                         else self._ask_remove(args.get("name", "")))
                if reply.pending:
                    self._tool_pending = reply.pending
                    return ("Pendiente de confirmación: la interfaz mostrará botones Sí/Cancelar al usuario. "
                            "Díselo; la acción NO se ha realizado todavía.")
                return reply.text
            if name == "remember":
                return self._remember(str(args.get("fact", ""))).text
        except Exception as exc:  # noqa: BLE001
            log.exception("Error en herramienta %s", name)
            return f"Error ejecutando {name}: {exc}"
        return f"Herramienta desconocida: {name}"

    # --- petición al modelo ---------------------------------------------
    class _ToolsRejected(Exception):
        pass

    class _ProviderError(Exception):
        pass

    def _chat(self, messages: list, tools: Optional[list], stream: bool, on_token):
        """Una petición al modelo. Devuelve (texto, [llamadas a herramientas])."""
        key = self._api_key()
        base = (self.settings.get("ai.base_url") or "https://api.openai.com/v1").rstrip("/")
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = f"Bearer {key}"
        payload = {"model": self.settings.get("ai.model", "gpt-4o-mini"), "messages": messages,
                   "temperature": float(self.settings.get("ai.temperature", 0.7))}
        if tools:
            payload["tools"] = tools
        if stream:
            payload["stream"] = True
        r = requests.post(f"{base}/chat/completions", headers=headers, json=payload, timeout=60, stream=stream)
        if r.status_code != 200:
            body = r.text[:300].lower()
            log.warning("IA devolvió %s: %s", r.status_code, body)
            if tools and r.status_code in (400, 404, 422) and ("tool" in body or "function" in body):
                raise self._ToolsRejected()
            raise self._ProviderError(PROVIDER_ERRORS.get(r.status_code, f"El proveedor de IA devolvió un error ({r.status_code})."))
        if not stream:
            msg = r.json()["choices"][0]["message"]
            calls = [{"id": c.get("id", ""), "name": c["function"]["name"], "arguments": c["function"].get("arguments", "")}
                     for c in (msg.get("tool_calls") or [])]
            return msg.get("content") or "", calls
        r.encoding = "utf-8"
        parts, calls = [], {}
        for line in r.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                choices = json.loads(data).get("choices") or []
            except ValueError:
                continue
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            if delta.get("content"):
                parts.append(delta["content"])
                if on_token:
                    on_token("".join(parts))
            for tc in delta.get("tool_calls") or []:
                slot = calls.setdefault(tc.get("index", 0), {"id": "", "name": "", "arguments": ""})
                if tc.get("id"):
                    slot["id"] = tc["id"]
                fn = tc.get("function") or {}
                if fn.get("name"):
                    slot["name"] = fn["name"]
                slot["arguments"] += fn.get("arguments") or ""
        return "".join(parts), [calls[i] for i in sorted(calls)]

    def _llm(self, text: str, history: List[dict], on_token=None) -> AssistantReply:
        if self.license is not None and not self.license.allows("ai_chat"):
            return AssistantReply("El chat libre con IA es una función de la licencia **Plus**. Los comandos locales "
                                  "(abrir juegos, horas, recomendaciones) siguen disponibles.")
        key = self._api_key()
        if key is None and not self._is_local_url():
            return AssistantReply(
                "Para charlar libremente necesito conectarme a un modelo de IA. Añade tu clave en "
                "**Ajustes → Inteligencia artificial** (o usa Ollama en local). Mientras tanto puedo abrir juegos, "
                "contar tus horas y recomendarte juegos: escribe «ayuda» para ver ejemplos.")
        self._tool_pending = None
        use_tools = bool(self.settings.get("ai.use_tools", True)) and not getattr(self, "_no_tools", False)
        stream = bool(self.settings.get("ai.stream", True))
        launched: List[str] = []
        messages = [{"role": "system", "content": self._system_prompt(use_tools)}]
        messages += [m for m in history if m["role"] in ("user", "assistant")][-10:]
        messages.append({"role": "user", "content": text})
        content = ""
        try:
            for _ in range(5):
                try:
                    content, calls = self._chat(messages, self.TOOLS if use_tools else None, stream, on_token)
                except self._ToolsRejected:
                    log.info("El modelo no admite herramientas; se usa el modo de texto")
                    self._no_tools, use_tools = True, False
                    messages[0]["content"] = self._system_prompt(False)
                    continue
                if not calls:
                    break
                messages.append({"role": "assistant", "content": content or None, "tool_calls": [
                    {"id": c["id"] or f"call_{i}", "type": "function",
                     "function": {"name": c["name"], "arguments": c["arguments"] or "{}"}}
                    for i, c in enumerate(calls)]})
                for i, c in enumerate(calls):
                    try:
                        args = json.loads(c["arguments"] or "{}")
                    except ValueError:
                        args = {}
                    if c["name"] == "open_target" and launched:
                        time.sleep(2.5)
                    messages.append({"role": "tool", "tool_call_id": c["id"] or f"call_{i}",
                                     "content": self._run_tool(c["name"], args, launched)})
        except self._ProviderError as exc:
            return AssistantReply(str(exc))
        except requests.ConnectionError:
            return AssistantReply("No pude conectar con el servicio de IA. Comprueba tu conexión o la dirección "
                                  "en Ajustes.")
        except requests.Timeout:
            return AssistantReply("El servicio de IA tardó demasiado en responder. Inténtalo de nuevo.")
        except requests.RequestException as exc:
            log.warning("Error de red con la IA: %s", exc)
            return AssistantReply("Hubo un problema de red al consultar la IA.")
        except (ValueError, KeyError, IndexError):
            return AssistantReply("La respuesta de la IA no tuvo el formato esperado.")

        # Modo texto (sin herramientas): acciones con la etiqueta [[ABRIR: x]]
        names = ACTION_RE.findall(content)
        clean = ACTION_RE.sub("", content).strip()
        notes = []
        for i, name in enumerate(names[:4]):
            target, _ = self.resolve(name)
            if not target:
                notes.append(f"⚠️ No encuentro «{name}» en tu biblioteca.")
                continue
            if i:
                time.sleep(2.5)
            ok, msg = self._launch(target)
            notes.append(("✅ " if ok else "⚠️ ") + msg)
            if ok:
                launched.append(self._target_label(target))
        if notes:
            clean = (clean + "\n" + "\n".join(notes)).strip()
        if launched and use_tools:
            clean = (clean + "\n" + "\n".join("✅ Abierto: " + n for n in launched)).strip()
        return AssistantReply(clean or "…", launched, used_llm=True, pending=self._tool_pending)

    def test_connection(self) -> str:
        """Usado por el botón 'Probar conexión' de Ajustes. Devuelve un mensaje legible."""
        key = self._api_key()
        if key is None and not self._is_local_url():
            return "Falta la clave API."
        base = (self.settings.get("ai.base_url") or "").rstrip("/")
        try:
            r = requests.post(
                f"{base}/chat/completions", timeout=30,
                headers={"Authorization": f"Bearer {key}"} if key else {},
                json={"model": self.settings.get("ai.model"), "max_tokens": 5,
                      "messages": [{"role": "user", "content": "Responde solo: ok"}]})
        except requests.RequestException as exc:
            return f"No se pudo conectar: {exc.__class__.__name__}"
        if r.status_code == 200:
            return "Conexión correcta ✔"
        return PROVIDER_ERRORS.get(r.status_code, f"Error {r.status_code} del proveedor.")
