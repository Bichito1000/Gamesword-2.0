import unittest

import ai.assistant as A
from core.models import Game
from tests.common import FakePlatforms, FakeTracker, make_env

A.time.sleep = lambda s: None


class AssistantTests(unittest.TestCase):
    def setUp(self):
        _, self.db, self.settings = make_env()
        for name, plat in (("Fortnite", "epic"), ("Rocket League", "epic"), ("Plants vs Zombies", "steam")):
            self.db.add_game(Game(name=name, platform=plat))
        sid = self.db.start_session(1)
        self.db.update_session(sid, 5400, True)
        self.tracker = FakeTracker()
        self.a = A.GamesAssistant(self.db, self.settings, self.tracker, FakePlatforms())

    def test_open_simple_and_chained(self):
        r = self.a.respond("Ábreme Fortnite")
        self.assertEqual(r.launched, ["Fortnite"])
        r = self.a.respond("Abre Discord y después Rocket League")
        self.assertEqual(r.launched, ["Discord", "Rocket League"])
        self.assertIn("Rocket League", self.tracker.played)

    def test_comma_separated_with_missing_game(self):
        r = self.a.respond("abre discord, fortnite y minecraft")
        self.assertIn("Fortnite", r.launched)
        self.assertIn("minecraft", r.text.lower())

    def test_game_names_containing_y_or_vs_still_work(self):
        self.assertEqual(self.a.respond("abre plants vs zombies").launched, ["Plants vs Zombies"])

    def test_playtime_questions(self):
        self.assertIn("1h 30m", self.a.respond("¿Cuántas horas he jugado esta semana?").text)
        self.assertIn("Fortnite", self.a.respond("cuántas horas he jugado a fortnite en total").text)

    def test_library_and_recommendations(self):
        self.assertIn("3 juegos", self.a.respond("¿Qué juegos tengo instalados?").text)
        r = self.a.respond("Quiero jugar a algo parecido a GTA V")
        self.assertIn("Red Dead Redemption 2", r.text)
        r = self.a.respond("Busca juegos cooperativos para jugar con amigos")
        self.assertIn("•", r.text)

    def test_without_api_key_falls_back_to_help(self):
        r = self.a.respond("¿Cómo mejoro mis FPS?")
        self.assertIn("Ajustes", r.text)

    def test_history_is_saved(self):
        self.a.respond("ayuda")
        self.assertEqual([m["role"] for m in self.db.get_chat()], ["user", "assistant"])


if __name__ == "__main__":
    unittest.main()
