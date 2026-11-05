import json
import pathlib
import sqlite3
import tempfile
import unittest

import core.epic_import as ei
import core.galaxy_import as gi
import core.game_detector as gd
import core.library_sync as ls
import core.steam_import as si
from core.models import DetectedGame, Game
from tests.common import make_env


def make_galaxy_db(path):
    c = sqlite3.connect(path)
    c.executescript("""
        CREATE TABLE GamePieceTypes(id INTEGER PRIMARY KEY, type TEXT);
        CREATE TABLE GamePieces(releaseKey TEXT, gamePieceTypeId INTEGER, value TEXT);
        CREATE TABLE LibraryReleases(releaseKey TEXT);
        CREATE TABLE UserReleaseProperties(releaseKey TEXT, isHidden INTEGER);
        INSERT INTO GamePieceTypes VALUES (1,'originalTitle'),(2,'title');
    """)
    rows = [("steam_220", "Half-Life 2"), ("epic_Sugar", "Rocket League"), ("uplay_3539", "Far Cry 5"),
            ("origin_X1", "FIFA 23"), ("xboxone_abc", "Forza Horizon 5"), ("amazon_zz", "Otra tienda"),
            ("steam_999", "Oculto")]
    for key, title in rows:
        c.execute("INSERT INTO LibraryReleases VALUES (?)", (key,))
        c.execute("INSERT INTO GamePieces VALUES (?,?,?)", (key, 1, json.dumps({"title": title})))
    c.execute("INSERT INTO UserReleaseProperties VALUES ('steam_999',1)")
    c.commit()
    c.close()


class OwnedLibraryTests(unittest.TestCase):
    def setUp(self):
        self.tmp, self.db, self.settings = make_env()

    def test_galaxy_reads_all_platforms_and_hides_hidden(self):
        p = self.tmp / "galaxy-2.0.db"
        make_galaxy_db(p)
        owned = gi.read_owned(p)
        plats = {g.name: g.platform for g in owned}
        self.assertEqual(plats["Half-Life 2"], "steam")
        self.assertEqual(plats["Far Cry 5"], "ubisoft")
        self.assertEqual(plats["FIFA 23"], "ea")
        self.assertEqual(plats["Forza Horizon 5"], "xbox")
        self.assertNotIn("Oculto", plats)
        self.assertNotIn("Otra tienda", plats)
        self.assertTrue(all(not g.installed for g in owned))
        self.assertEqual(gi.read_owned(self.tmp / "no_existe.db"), [])

    def test_owned_games_do_not_duplicate_installed_ones(self):
        self.db.upsert_detected([DetectedGame("Rocket League", "epic", "Sugar", launch_uri="x://run")])
        self.db.upsert_detected([DetectedGame("Rocket League", "epic", "otro-id", installed=False),
                                 DetectedGame("Half-Life 2", "steam", "220", installed=False)])
        games = {g.name: g for g in self.db.list_games()}
        self.assertEqual(len(games), 2)
        self.assertEqual(games["Rocket League"].installed, 1)         # sigue instalado
        self.assertEqual(games["Half-Life 2"].installed, 0)

    def test_legendary_parsing_and_errors(self):
        class R:
            stdout = json.dumps([{"app_name": "Sugar", "app_title": "Rocket League"},
                                 {"app_name": "Fortnite", "metadata": {"title": "Fortnite"}}])
        old_run, old_cmd = ei.subprocess.run, ei.legendary_command
        ei.legendary_command = lambda: ["legendary"]
        ei.subprocess.run = lambda *a, **k: R()
        try:
            owned = ei.read_owned()
            self.assertEqual([g.name for g in owned], ["Rocket League", "Fortnite"])
            self.assertTrue(all(g.platform == "epic" and not g.installed for g in owned))
            R.stdout = "not json"
            with self.assertRaises(ei.EpicImportError):
                ei.read_owned()
            ei.legendary_command = lambda: []
            with self.assertRaises(ei.EpicImportError):
                ei.read_owned()
        finally:
            ei.subprocess.run, ei.legendary_command = old_run, old_cmd

    def test_steam_user_id_from_loginusers(self):
        root = pathlib.Path(tempfile.mkdtemp())
        (root / "config").mkdir()
        (root / "config" / "loginusers.vdf").write_text(
            '"users"\n{\n"76561198000000001"\n{\n"AccountName" "a"\n"MostRecent" "0"\n}\n'
            '"76561198000000002"\n{\n"AccountName" "b"\n"MostRecent" "1"\n}\n}')
        old = gd.steam_root
        gd.steam_root = lambda: root
        try:
            self.assertEqual(gd.steam_user_id(), "76561198000000002")
        finally:
            gd.steam_root = old

    def test_sync_all_combines_sources_and_marks_uninstalled(self):
        self.db.upsert_detected([DetectedGame("Viejo", "steam", "50")])      # estaba instalado, ya no
        old = (gd.detect_all, gd.steam_user_id, gi.read_owned, ei.read_owned, si.import_playtime, ls.import_playtime)
        gd.detect_all = lambda: [DetectedGame("Hades", "steam", "1145360")]
        gd.steam_user_id = lambda: "7" * 17
        gi.read_owned = lambda *a: [DetectedGame("Far Cry 5", "ubisoft", "3539", installed=False)]
        ei.read_owned = lambda: [DetectedGame("Rocket League", "epic", "Sugar", installed=False)]
        calls = {}

        def fake_import(db, key, sid, add_owned=False):
            calls.update(key=key, sid=sid, add_owned=add_owned)
            db.upsert_detected([DetectedGame("Portal 2", "steam", "620", installed=False)])
            return si.ImportResult(matched=1, updated=1, added=1, total_owned=3)
        ls.import_playtime = fake_import
        self.settings.set("steam.api_key", "KEY")
        try:
            lines = ls.sync_all(self.db, self.settings)
        finally:
            gd.detect_all, gd.steam_user_id, gi.read_owned, ei.read_owned, si.import_playtime, ls.import_playtime = old
        self.assertEqual(calls, {"key": "KEY", "sid": "7" * 17, "add_owned": True})
        by = {g.name: g.installed for g in self.db.list_games()}
        self.assertEqual(by, {"Viejo": 0, "Hades": 1, "Portal 2": 0, "Far Cry 5": 0, "Rocket League": 0})
        self.assertEqual(len(lines), 4)
        self.assertEqual(len(self.db.list_games(installed=False)), 4)
        self.assertEqual(self.db.count_installed(), 1)

    def test_sync_without_steam_key_explains_what_to_do(self):
        old = (gd.detect_all, gi.read_owned, ei.read_owned)
        gd.detect_all = lambda: []
        gi.read_owned = lambda *a: []
        ei.read_owned = lambda: (_ for _ in ()).throw(ei.EpicImportError("instala legendary"))
        try:
            lines = ls.sync_all(self.db, self.settings)
        finally:
            gd.detect_all, gi.read_owned, ei.read_owned = old
        self.assertTrue(any("clave de API" in l for l in lines))
        self.assertTrue(any("legendary" in l for l in lines))

    def test_steam_import_adds_uninstalled_with_install_uri(self):
        class R:
            status_code = 200
            def json(self):
                return {"response": {"games": [{"appid": 620, "name": "Portal 2", "playtime_forever": 120}]}}
        old = si.requests.get
        si.requests.get = lambda *a, **k: R()
        try:
            si.import_playtime(self.db, "K", "7" * 17, add_owned=True)
        finally:
            si.requests.get = old
        g = self.db.list_games()[0]
        self.assertEqual((g.installed, g.launch_uri, g.total_seconds), (0, "steam://install/620", 7200))


if __name__ == "__main__":
    unittest.main()
