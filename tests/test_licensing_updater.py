import hashlib
import json
import os
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from core import ed25519, updater
from core.licensing import encode_license, verify_license


class Ed25519Tests(unittest.TestCase):
    def test_rfc8032_vector(self):          # Test 1 del RFC 8032
        sk = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
        pk = bytes.fromhex("d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a")
        sig = bytes.fromhex("e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b")
        self.assertEqual(ed25519.public_key(sk), pk)
        self.assertEqual(ed25519.sign(sk, b""), sig)
        self.assertTrue(ed25519.verify(pk, b"", sig))
        self.assertFalse(ed25519.verify(pk, b"x", sig))


class LicenseTests(unittest.TestCase):
    def setUp(self):
        self.sk = os.urandom(32)
        self.pub = ed25519.public_key(self.sk).hex()

    def issue(self, **extra):
        payload = {"tier": "plus", "name": "Ana", **extra}
        body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        return encode_license(payload, ed25519.sign(self.sk, body))

    def test_valid_tampered_expired(self):
        lic = self.issue(exp=int(time.time()) + 1000)
        self.assertTrue(verify_license(lic, self.pub).valid)
        self.assertFalse(verify_license(lic[:-3] + "AAA", self.pub).valid)
        self.assertFalse(verify_license(self.issue(exp=int(time.time()) - 5), self.pub).valid)
        self.assertFalse(verify_license(lic, ed25519.public_key(os.urandom(32)).hex()).valid)
        self.assertFalse(verify_license("", self.pub).valid)


class UpdaterTests(unittest.TestCase):
    PAYLOAD = b"INSTALADOR" * 500

    @classmethod
    def setUpClass(cls):
        cls.sha = {"v": hashlib.sha256(cls.PAYLOAD).hexdigest()}
        outer = cls

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                if self.path.endswith("update.json"):
                    body = json.dumps({"version": "1.2.0", "sha256": outer.sha["v"],
                                       "url": f"http://127.0.0.1:{self.server.server_address[1]}/setup.exe"}).encode()
                else:
                    body = outer.PAYLOAD
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        cls.srv = HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.srv.server_address[1]}/update.json"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def test_versions(self):
        self.assertTrue(updater.parse_version("1.10.0") > updater.parse_version("1.9.9"))
        self.assertIsNone(updater.check(self.url, "1.2.0"))
        self.assertEqual(updater.check(self.url, "1.1.0").version, "1.2.0")

    def test_download_verifies_hash(self):
        self.sha["v"] = hashlib.sha256(self.PAYLOAD).hexdigest()
        self.assertEqual(updater.download(updater.check(self.url, "1.1.0")).stat().st_size, len(self.PAYLOAD))
        self.sha["v"] = "0" * 64
        with self.assertRaises(updater.UpdateError):
            updater.download(updater.check(self.url, "1.1.0"))

    def test_rejects_insecure_manifest(self):
        with self.assertRaises(updater.UpdateError):
            updater.check("http://evil.example/update.json", "1.0")


if __name__ == "__main__":
    unittest.main()
