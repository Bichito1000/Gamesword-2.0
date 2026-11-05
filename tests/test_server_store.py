import unittest

from server.store import Store, StoreError
from tests.common import make_env


class ServerStoreTests(unittest.TestCase):
    def setUp(self):
        tmp, _, _ = make_env()
        self.s = Store(tmp / "server.db")
        self.a = self.s.register("Ana", "contraseña1")
        self.b = self.s.register("Beto", "otraClave99")

    def err(self, fn, *args):
        with self.assertRaises(StoreError) as cm:
            fn(*args)
        return cm.exception.status

    def test_accounts(self):
        self.assertEqual(self.err(self.s.register, "Eva", "corta"), 400)
        self.assertEqual(self.err(self.s.register, "ana", "contraseña1"), 409)
        self.assertEqual(self.s.login("Ana", "contraseña1")["user_id"], self.a["user_id"])
        self.assertEqual(self.err(self.s.login, "Ana", "mala"), 401)
        self.assertIsNone(self.s.user_by_token("falso"))
        self.s.logout(self.a["token"])
        self.assertIsNone(self.s.user_by_token(self.a["token"]))

    def test_brute_force_lockout(self):
        for _ in range(8):
            self.err(self.s.login, "Ana", "mala", "9.9.9.9")
        self.assertEqual(self.err(self.s.login, "Ana", "contraseña1", "9.9.9.9"), 429)

    def test_friends_chat_invites(self):
        self.s.add_friend(self.a["user_id"], self.b["friend_code"])
        self.assertEqual(self.err(self.s.add_friend, self.a["user_id"], self.a["friend_code"]), 400)
        g = self.s.create_group(self.a["user_id"], "Coop", "Deep Rock")
        self.assertEqual(self.err(self.s.messages, self.b["user_id"], g["id"]), 403)
        self.s.join_group(self.b["user_id"], g["code"])
        m = self.s.post_message(self.b["user_id"], g["id"], "¡Hola!")
        self.s.post_message(self.a["user_id"], g["id"], "Entro")
        self.assertEqual(len(self.s.messages(self.a["user_id"], g["id"])), 2)
        self.assertEqual(len(self.s.messages(self.a["user_id"], g["id"], after=m["id"])), 1)
        self.s.send_invite(self.a["user_id"], self.b["user_id"], "Deep Rock", "¿Jugamos?")
        self.assertEqual(len(self.s.pending_invites(self.b["user_id"])), 1)
        self.assertEqual(self.s.pending_invites(self.b["user_id"]), [])
        c = self.s.register("Carla", "claveSegura1")
        self.assertEqual(self.err(self.s.send_invite, self.a["user_id"], c["user_id"], "x", ""), 403)

    def test_empty_group_is_deleted(self):
        g = self.s.create_group(self.a["user_id"], "Solo", "")
        self.s.leave_group(self.a["user_id"], g["id"])
        self.assertEqual(self.s.groups(self.a["user_id"]), [])


if __name__ == "__main__":
    unittest.main()
