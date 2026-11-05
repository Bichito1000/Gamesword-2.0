import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.settings import Settings            # noqa: E402
from core.database import DatabaseManager       # noqa: E402


def make_env():
    tmp = pathlib.Path(tempfile.mkdtemp())
    db = DatabaseManager(tmp / "t.db")
    db.init()
    return tmp, db, Settings(tmp / "s.json")


class FakeTracker:
    def __init__(self):
        self.played = []
        self.running = {}          # game_id -> (nombre, inicio)
        self.closed = []

    def active(self):
        return dict(self.running)

    def close_game(self, game_id):
        self.closed.append(game_id)
        return 2

    def play(self, game):
        self.played.append(game.name)
        return True, f"Iniciando {game.name}…"


class FakePlatforms:
    def resolve_alias(self, text):
        return {"discord": "discord", "steam": "steam"}.get(text)

    def open(self, key):
        return True, f"Abriendo {key}…"

    def installed_keys(self):
        return ["steam", "discord"]
