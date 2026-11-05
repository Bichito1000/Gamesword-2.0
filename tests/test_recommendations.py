import unittest

from ai.recommendations import by_tags, find_in_catalog, similar_to, tags_from_text
from ai.voice import extract_after_wake
from tests.common import make_env


class RecommendationTests(unittest.TestCase):
    def test_aliases_and_similarity(self):
        e = find_in_catalog("GTA V")
        self.assertEqual(e["name"], "Grand Theft Auto V")
        names = [g["name"] for g in similar_to(e, 5)]
        self.assertIn("Red Dead Redemption 2", names)
        self.assertNotIn("Grand Theft Auto V", names)
        self.assertIsNone(find_in_catalog("xyzzy plugh"))

    def test_owned_games_are_excluded(self):
        e = find_in_catalog("GTA V")
        names = [g["name"] for g in similar_to(e, 30, owned_names=["Red Dead Redemption 2"])]
        self.assertNotIn("Red Dead Redemption 2", names)

    def test_coop_horror(self):
        tags = tags_from_text("juegos cooperativos de terror")
        self.assertEqual(set(tags), {"cooperativo", "terror"})
        for g in by_tags(tags, 10):
            self.assertTrue(g["coop"] and "terror" in g["tags"])


class WakeWordTests(unittest.TestCase):
    def test_extract(self):
        self.assertEqual(extract_after_wake("Oye Gamesword ábreme Fortnite"), "abreme fortnite")
        self.assertEqual(extract_after_wake("hey games word, abre discord"), "abre discord")
        self.assertEqual(extract_after_wake("Gamesword"), "")
        self.assertIsNone(extract_after_wake("ábreme fortnite"))
        self.assertIsNone(extract_after_wake("hola qué tal gamesword"))


if __name__ == "__main__":
    unittest.main()
