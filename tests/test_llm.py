"""Prueba el cliente de IA (herramientas + streaming + fallback) contra un servidor falso local."""
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

import ai.assistant as A
from core.models import Game
from tests.common import FakePlatforms, FakeTracker, make_env

A.time.sleep = lambda s: None
STATE = {"reject_tools": False}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _sse(self, chunks):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for c in chunks:
            self.wfile.write(b"data: " + json.dumps({"choices": [{"delta": c}]}).encode() + b"\n\n")
        self.wfile.write(b"data: [DONE]\n\n")

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        done_tool = any(m["role"] == "tool" for m in body["messages"])
        if STATE["reject_tools"] and "tools" in body:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b'{"error":"tools not supported by this function"}')
            return
        if "tools" in body and not done_tool:
            parts = [{"tool_calls": [{"index": 0, "id": "c1", "function": {"name": "open_target", "arguments": '{"name":"fort'}}]},
                     {"tool_calls": [{"index": 0, "function": {"arguments": 'nite"}'}}]}]
            if body.get("stream"):
                return self._sse(parts)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps({"choices": [{"message": {"content": None, "tool_calls": [
                {"id": "c1", "function": {"name": "open_target", "arguments": '{"name":"fortnite"}'}}]}}]}).encode())
            return
        text = "Listo, ya te lo abro" if done_tool else "Baja las sombras. [[ABRIR: Fortnite]]"
        if body.get("stream"):
            return self._sse([{"content": w + " "} for w in text.split(" ")])
        self.send_response(200)
        self.end_headers()
        self.wfile.write(json.dumps({"choices": [{"message": {"content": text}}]}).encode())


class LLMTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        STATE["reject_tools"] = False
        _, self.db, self.settings = make_env()
        self.settings.set("ai.base_url", f"http://127.0.0.1:{self.srv.server_address[1]}")
        self.settings.set("ai.api_key", "k")
        self.db.add_game(Game(name="Fortnite", platform="epic"))
        self.tracker = FakeTracker()
        self.a = A.GamesAssistant(self.db, self.settings, self.tracker, FakePlatforms())

    def test_tool_calling_with_and_without_streaming(self):
        for stream in (True, False):
            self.tracker.played.clear()
            self.settings.set("ai.stream", stream)
            tokens = []
            r = self.a.respond("me aburro, lanza fortnite", on_token=tokens.append)
            self.assertEqual(self.tracker.played, ["Fortnite"])
            self.assertIn("Listo", r.text)
            self.assertEqual(bool(tokens), stream)

    def test_falls_back_to_text_mode_when_tools_rejected(self):
        STATE["reject_tools"] = True
        r = self.a.respond("mejora mis fps")
        self.assertTrue(self.a._no_tools)
        self.assertEqual(self.tracker.played, ["Fortnite"])
        self.assertIn("sombras", r.text)

    def test_license_gate(self):
        class Locked:
            def allows(self, f):
                return False
        self.a.license = Locked()
        self.assertIn("Plus", self.a.respond("me aburro, lanza fortnite").text)


if __name__ == "__main__":
    unittest.main()
