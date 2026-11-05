import json
import sqlite3
import unittest
import zipfile
from datetime import datetime

from core import backup
from core.models import Game
from core.progress import ProgressManager, level_for, xp_for_level
from tests.common import make_env


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp, self.db, self.settings = make_env()
        backup.data_dir = lambda: self.tmp           # aislar las copias en la carpeta temporal
        self.gid = self.db.add_game(Game(name="Hades", platform="steam"))
        self.settings.set("ai.api_key", "sk-secreto")

    def test_backup_has_no_secrets_and_restores(self):
        z = backup.create_backup(self.db.path, self.settings, "2.0.0")
        with zipfile.ZipFile(z) as zf:
            self.assertEqual(set(zf.namelist()), {"gamesword.db", "settings.json", "manifest.json"})
            self.assertNotIn("sk-secreto", zf.read("settings.json").decode())
        self.db.delete_game(self.gid)
        self.assertEqual(self.db.count_games(), 0)
        backup.restore_backup(z, self.db.path, self.settings)
        self.assertEqual([g.name for g in self.db.list_games()], ["Hades"])
        self.assertEqual(self.settings.get("ai.api_key"), "sk-secreto")      # la clave local NO se pisa

    def test_rotation_and_due(self):
        for _ in range(5):
            backup.create_backup(self.db.path, self.settings, keep=3)
        self.assertEqual(len(backup.list_backups()), 3)
        self.assertFalse(backup.backup_due(self.settings))
        self.settings.set("app.last_backup", "2000-01-01T00:00:00")
        self.assertTrue(backup.backup_due(self.settings))

    def test_corrupt_zip_is_rejected_and_nothing_changes(self):
        bad = self.tmp / "mala.zip"
        bad.write_bytes(b"esto no es un zip")
        with self.assertRaises(backup.BackupError):
            backup.restore_backup(bad, self.db.path, self.settings)
        self.assertEqual(self.db.count_games(), 1)

    def test_corrupt_database_is_recovered_from_latest_backup(self):
        backup.create_backup(self.db.path, self.settings, "2.0.0")
        self.db.path.write_bytes(b"SQLite format 3\x00" + b"\xff" * 500)       # corrupción
        self.assertFalse(backup.check_integrity(self.db.path)[0])
        msg = backup.recover_if_corrupt(self.db.path)
        self.assertIn("restaurado", msg)
        self.db.init()
        self.assertEqual([g.name for g in self.db.list_games()], ["Hades"])
        self.assertIsNone(backup.recover_if_corrupt(self.db.path))

    def test_corrupt_database_without_backups_starts_clean(self):
        self.db.path.write_bytes(b"basura" * 100)
        self.assertIn("nueva", backup.recover_if_corrupt(self.db.path))
        self.db.init()
        self.assertEqual(self.db.count_games(), 0)


class CollectionsTests(unittest.TestCase):
    def test_collections_flow(self):
        _, db, _ = make_env()
        a, b = db.add_game(Game(name="A")), db.add_game(Game(name="B"))
        cid = db.create_collection("Coop")
        db.set_in_collection(cid, a, True)
        db.set_in_collection(cid, b, True)
        self.assertEqual({g.name for g in db.list_games(collection_id=cid)}, {"A", "B"})
        db.set_in_collection(cid, b, False)
        self.assertEqual(db.list_collections(), [(cid, "Coop", 1)])
        with self.assertRaises(ValueError):
            db.create_collection("coop")
        with self.assertRaises(ValueError):
            db.create_collection("   ")
        db.rename_collection(cid, "Con amigos")
        db.delete_collection(cid)
        self.assertEqual(db.list_collections(), [])
        self.assertEqual(db.count_games(), 2)                 # borrar la colección no borra juegos


class ProgressTests(unittest.TestCase):
    def setUp(self):
        _, self.db, self.settings = make_env()
        self.pm = ProgressManager(self.db, self.settings)
        self.unlocked = []
        self.pm.on_unlock = self.unlocked.extend

    def test_level_curve(self):
        self.assertEqual([xp_for_level(n) for n in (1, 2, 3, 4)], [0, 100, 300, 600])
        self.assertEqual([level_for(x) for x in (0, 99, 100, 299, 300, 600)], [1, 1, 2, 2, 3, 4])

    def test_unlocks_once_and_grant_xp(self):
        gid = self.db.add_game(Game(name="A"))
        sid = self.db.start_session(gid)
        self.db.update_session(sid, 3700, True)
        first = {u.key for u in self.pm.evaluate()}
        self.assertIn("first_session", first)
        self.assertIn("day_play30", first)
        self.assertEqual(self.pm.evaluate(), [])              # nada repetido
        snap = self.pm.snapshot()
        # La XP = 10 por hora + recompensas realmente desbloqueadas. No se fija un número a mano porque, según la hora
        # a la que se ejecute el test (p. ej. de madrugada), se desbloquea también «Noctámbulo».
        self.assertEqual(snap["xp"], int(3700 / 3600 * 10) + self.db.xp_from_rewards())
        self.assertGreaterEqual(self.db.xp_from_rewards(), 50 + 30)       # Primer paso + Calentamiento
        self.assertEqual(snap["level"], 1 if snap["xp"] < 100 else 2)

    def test_usage_achievements_via_counters(self):
        self.pm.record("ai_messages")
        self.pm.record("backups")
        keys = {u.key for u in self.unlocked}
        self.assertTrue({"first_ai", "safe"} <= keys)

    def test_imported_hours_give_xp_but_not_sessions(self):
        gid = self.db.add_game(Game(name="A", platform="steam", external_id="1"))
        self.db.set_imported_seconds(gid, 100 * 3600)
        snap = self.pm.snapshot()
        self.assertEqual(snap["xp"], 1000)
        self.assertNotIn("first_session", {u.key for u in self.pm.evaluate()})
        self.assertIn("h100", {u.key for u in self.pm.evaluate() + self.unlocked})

    def test_weekly_challenge_progress(self):
        for _ in range(2):
            gid = self.db.add_game(Game(name=f"G{_}"))
            self.db.log_activity("launch", "x", 0, str(gid))
        ch = {c["key"]: c for c in self.pm.snapshot()["challenges"]}
        self.assertEqual((ch["week_3games"]["value"], ch["day_launch2"]["done"]), (2, False))
        self.db.log_activity("launch", "x", 0, "99")
        self.pm.evaluate()
        ch = {c["key"]: c for c in self.pm.snapshot()["challenges"]}
        self.assertTrue(ch["week_3games"]["done"])


if __name__ == "__main__":
    unittest.main()
