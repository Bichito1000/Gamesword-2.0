import json
import os
import pathlib
import tempfile
import unittest

import core.game_detector as gd
import core.steam_import as si
from core.models import Game
from tests.common import make_env


class DetectorTests(unittest.TestCase):
    def test_steam_multi_library_and_epic_and_folder(self):
        tmp = pathlib.Path(tempfile.mkdtemp())
        root, lib2 = tmp / "Steam", tmp / "Lib2"
        (root / "steamapps" / "common" / "Hades").mkdir(parents=True)
        (lib2 / "steamapps" / "common" / "Terraria").mkdir(parents=True)
        esc = lambda p: str(p).replace("\\", "\\\\")
        (root / "steamapps" / "libraryfolders.vdf").write_text(
            f'"libraryfolders"\n{{\n "0"\n {{\n  "path"\t"{esc(root)}"\n }}\n "1"\n {{\n  "path"\t"{esc(lib2)}"\n }}\n}}')
        (root / "steamapps" / "appmanifest_1.acf").write_text('"AppState"\n{\n"appid" "1"\n"name" "Hades"\n"installdir" "Hades"\n}')
        (lib2 / "steamapps" / "appmanifest_2.acf").write_text('"AppState"\n{\n"appid" "2"\n"name" "Terraria"\n"installdir" "Terraria"\n}')
        (root / "steamapps" / "appmanifest_228980.acf").write_text('"AppState"\n{\n"appid" "228980"\n"name" "Steamworks Common Redistributables"\n}')
        old = gd.steam_root
        gd.steam_root = lambda: root
        try:
            self.assertEqual(sorted(g.name for g in gd.detect_steam()), ["Hades", "Terraria"])
        finally:
            gd.steam_root = old
        man = tmp / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests"
        man.mkdir(parents=True)
        (man / "a.item").write_text(json.dumps({"DisplayName": "Rocket League", "AppName": "Sugar", "InstallLocation": "C:\\RL"}))
        (man / "b.item").write_text(json.dumps({"DisplayName": "DLC", "AppName": "d", "MainGameAppName": "Sugar"}))
        os.environ["PROGRAMDATA"] = str(tmp)
        self.assertEqual([g.name for g in gd.detect_epic()], ["Rocket League"])
        game = tmp / "Juegos" / "Mi Juego"
        game.mkdir(parents=True)
        (game / "MiJuego.exe").write_bytes(b"x" * 100)
        (game / "unins000.exe").write_bytes(b"x" * 900)
        found = gd.scan_folder(str(tmp / "Juegos"))
        self.assertEqual(pathlib.Path(found[0].exe_path).name, "MiJuego.exe")


class SteamImportTests(unittest.TestCase):
    def test_import_does_not_double_count(self):
        _, db, _ = make_env()
        gid = db.add_game(Game(name="Hades", platform="steam", external_id="1145360"))
        sid = db.start_session(gid)
        db.update_session(sid, 3600, True)

        class R:
            status_code = 200
            def json(self):
                return {"response": {"games": [{"appid": 1145360, "name": "Hades", "playtime_forever": 600},
                                               {"appid": 5, "name": "Otro", "playtime_forever": 60}]}}
        old = si.requests.get
        si.requests.get = lambda *a, **k: R()
        try:
            r = si.import_playtime(db, "K", "7" * 17, add_owned=True)
        finally:
            si.requests.get = old
        self.assertEqual((r.updated, r.added), (2, 1))
        self.assertEqual(db.get_game(gid).total_seconds, 36000)        # 600 min exactos, sin duplicar
        with self.assertRaises(si.SteamImportError):
            si.import_playtime(db, "", "x")


if __name__ == "__main__":
    unittest.main()
