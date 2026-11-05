import unittest

from tests.common import make_env
from core.models import DetectedGame, Game


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        _, self.db, _ = make_env()

    def test_sessions_and_totals(self):
        gid = self.db.add_game(Game(name="A", platform="steam"))
        sid = self.db.start_session(gid)
        self.db.update_session(sid, 3700, True)
        g = self.db.list_games()[0]
        self.assertEqual((g.total_seconds, g.sessions), (3700, 1))
        self.assertEqual(self.db.total_seconds(7), 3700)
        self.assertEqual(self.db.top_games()[0][2], 3700)

    def test_detected_games_hidden_after_delete(self):
        det = [DetectedGame("Hades", "steam", "1")]
        self.assertEqual(self.db.upsert_detected(det), 1)
        self.assertEqual(self.db.upsert_detected(det), 0)
        self.db.delete_game(self.db.list_games()[0].id)
        self.assertEqual(self.db.count_games(), 0)
        self.assertEqual(self.db.upsert_detected(det), 0)          # no reaparece
        self.assertEqual(self.db.unhide_all(), 1)

    def test_manual_game_is_really_deleted(self):
        gid = self.db.add_game(Game(name="Manual"))
        self.db.delete_game(gid)
        self.assertIsNone(self.db.get_game(gid))

    def test_imported_seconds_do_not_count_as_sessions(self):
        gid = self.db.add_game(Game(name="A", platform="steam", external_id="9"))
        self.db.set_imported_seconds(gid, 36000)
        self.db.set_imported_seconds(gid, 72000)                   # idempotente
        g = self.db.get_game(gid)
        self.assertEqual((g.total_seconds, g.sessions, g.last_played), (72000, 0, None))
        self.assertEqual(self.db.recent_games(), [])
        self.assertEqual(self.db.achievement_facts()["sessions"], 0)

    def test_orphan_sessions_are_closed_on_init(self):
        gid = self.db.add_game(Game(name="A"))
        self.db.start_session(gid)
        self.db.init()
        with self.db.connect() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM sessions WHERE ended_at IS NULL").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
