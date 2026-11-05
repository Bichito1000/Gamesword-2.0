"""Discord Rich Presence («Jugando a …»). Necesita `pip install pypresence` y un Application ID de Discord."""
import queue
import threading
from typing import Callable, Optional

from utils.logger import get_logger

log = get_logger("presence")

try:
    from pypresence import Presence
except Exception:  # noqa: BLE001
    Presence = None


class RichPresence:
    def __init__(self, settings):
        self.settings = settings
        self._q: "queue.Queue[Optional[Callable]]" = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._rpc = None

    @property
    def available(self) -> bool:
        return Presence is not None

    @property
    def configured(self) -> bool:
        return bool((self.settings.get("discord.app_id", "") or "").strip())

    def _ensure_thread(self) -> None:
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._worker, daemon=True, name="presence")
            self._thread.start()

    def _worker(self) -> None:
        while True:
            job = self._q.get()
            if job is None:
                break
            try:
                job()
            except Exception as exc:  # noqa: BLE001  (Discord cerrado, tubería rota, etc.)
                log.info("Rich Presence no disponible: %s", exc)
                self._rpc = None

    def _connect(self):
        if self._rpc is None:
            rpc = Presence(self.settings.get("discord.app_id").strip())
            rpc.connect()
            self._rpc = rpc
        return self._rpc

    def set_playing(self, game: str, started_ts: float) -> None:
        if not (self.available and self.configured):
            return
        self._ensure_thread()
        self._q.put(lambda: self._connect().update(details=f"Jugando a {game}"[:128], state="con Gamesword",
                                                    start=int(started_ts), large_text=game[:128]))

    def clear(self) -> None:
        if not (self.available and self.configured) or self._rpc is None:
            return
        self._ensure_thread()
        self._q.put(lambda: self._rpc.clear() if self._rpc else None)

    def close(self) -> None:
        self._q.put(lambda: self._rpc.close() if self._rpc else None)
        self._q.put(None)
