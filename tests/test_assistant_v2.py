import unittest

import ai.assistant as A
from core.models import Game
from tests.common import FakePlatforms, FakeTracker, make_env

A.time.sleep = lambda s: None


class AssistantV2Tests(unittest.TestCase):
    def setUp(self):
        _, self.db, self.settings = make_env()
        for name, plat in (("Fortnite", "epic"), ("Rocket League", "epic"), ("Grand Theft Auto V", "steam")):
            self.db.add_game(Game(name=name, platform=plat))
        self.tracker = FakeTracker()
        self.a = A.GamesAssistant(self.db, self.settings, self.tracker, FakePlatforms())

    # ----- comprensión sin palabras exactas
    def test_flexible_phrasing(self):
        for phrase in ("Oye, ¿me abres Fortnite por favor?", "enciende fortnite", "quiero echar una partida a Fortnite",
                       "vamos a jugar al Fortnite", "lánzame fortnite", "Arranca el fortnite"):
            self.tracker.played.clear()
            self.a.respond(phrase)
            self.assertEqual(self.tracker.played, ["Fortnite"], phrase)

    # ----- confirmaciones
    def test_close_requires_confirmation(self):
        self.tracker.running = {1: ("Fortnite", 0)}
        r = self.a.respond("cierra el juego que tengo abierto")
        self.assertIsNotNone(r.pending)
        self.assertEqual(self.tracker.closed, [])                 # NO se cierra sin confirmar
        out = self.a.execute_pending(True)
        self.assertEqual(self.tracker.closed, [1])
        self.assertIn("Fortnite", out.text)

    def test_cancel_does_nothing(self):
        self.tracker.running = {1: ("Fortnite", 0)}
        self.a.respond("cierra fortnite")
        self.assertIn("no hago nada", self.a.execute_pending(False).text)
        self.assertEqual(self.tracker.closed, [])
        self.assertIn("ninguna acción", self.a.execute_pending(True).text)

    def test_close_without_running_game_and_ambiguity(self):
        self.assertIsNone(self.a.respond("cierra el juego").pending)
        self.tracker.running = {1: ("Fortnite", 0), 2: ("Rocket League", 0)}
        r = self.a.respond("cierra el juego")
        self.assertIsNone(r.pending)
        self.assertIn("cuál", r.text)

    def test_confirmation_expires(self):
        self.tracker.running = {1: ("Fortnite", 0)}
        self.a.respond("cierra fortnite")
        self.a._pending.created -= 400
        self.assertIn("caducó", self.a.execute_pending(True).text)
        self.assertEqual(self.tracker.closed, [])

    def test_remove_game_needs_confirmation(self):
        r = self.a.respond("quita Fortnite de mi biblioteca")
        self.assertIsNotNone(r.pending)
        self.assertEqual(self.db.count_games(), 3)
        self.a.execute_pending(True)
        self.assertEqual(self.db.count_games(), 2)

    # ----- memoria
    def test_memory_remember_recall_forget(self):
        self.assertIn("Anotado", self.a.respond("recuerda que prefiero los juegos de terror").text)
        self.assertIn("terror", self.a.respond("¿qué recuerdas de mí?").text)
        self.assertIn("1", self.a.respond("olvida lo de terror").text)
        self.assertEqual(self.db.list_memory(), [])

    def test_memory_clear_all_needs_confirmation(self):
        self.a.respond("recuerda que juego en un portátil")
        r = self.a.respond("olvida todo")
        self.assertIsNotNone(r.pending)
        self.assertEqual(len(self.db.list_memory()), 1)
        self.a.execute_pending(True)
        self.assertEqual(self.db.list_memory(), [])

    def test_memory_can_be_disabled(self):
        self.settings.set("ai.memory_enabled", False)
        self.assertIn("desactivada", self.a.respond("recuerda que me gusta el rol").text)
        self.assertEqual(self.db.list_memory(), [])

    # ----- comandos personalizados
    def test_custom_command(self):
        self.settings.set("ai.custom_commands", [{"phrase": "modo noche", "targets": ["Discord", "Rocket League"]}])
        r = self.a.respond("activa el modo noche")
        self.assertEqual(r.launched, ["Discord", "Rocket League"])
        self.assertIn("modo noche", r.text.lower())

    # ----- diagnóstico
    def test_pc_diagnosis(self):
        self.assertIn("Diagnóstico", self.a.respond("mi ordenador va lento, haz un diagnóstico").text)
        self.assertIn("CPU", self.a.respond("¿cómo está funcionando mi ordenador?").text)


if __name__ == "__main__":
    unittest.main()
