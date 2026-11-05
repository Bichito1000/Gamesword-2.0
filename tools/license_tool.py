"""Herramienta del AUTOR para crear y firmar licencias de Gamesword.

  python tools/license_tool.py keygen                       -> crea tools/private.key y muestra la clave pública
  python tools/license_tool.py issue --tier plus --name Ana --days 365
  python tools/license_tool.py check "<licencia>"

No distribuyas nunca tools/private.key ni esta carpeta.
"""
import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core import ed25519                                    # noqa: E402
from core.licensing import encode_license, verify_license   # noqa: E402

KEY_FILE = Path(__file__).resolve().parent / "private.key"


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("keygen")
    iss = sub.add_parser("issue")
    iss.add_argument("--tier", choices=["plus", "pro"], required=True)
    iss.add_argument("--name", required=True)
    iss.add_argument("--days", type=int, default=365, help="0 = sin caducidad")
    chk = sub.add_parser("check")
    chk.add_argument("license")
    a = ap.parse_args()

    if a.cmd == "keygen":
        if KEY_FILE.exists():
            sys.exit(f"Ya existe {KEY_FILE}. Bórralo solo si quieres invalidar TODAS las licencias emitidas.")
        secret = os.urandom(32)
        KEY_FILE.write_text(secret.hex())
        print("Clave privada guardada en", KEY_FILE)
        print("Pega esta clave PÚBLICA en core/licensing.py -> PUBLIC_KEY_HEX:\n")
        print(ed25519.public_key(secret).hex())
    elif a.cmd == "issue":
        if not KEY_FILE.exists():
            sys.exit("Primero ejecuta: python tools/license_tool.py keygen")
        secret = bytes.fromhex(KEY_FILE.read_text().strip())
        payload = {"tier": a.tier, "name": a.name, "iat": int(time.time()),
                   "exp": int(time.time() + a.days * 86400) if a.days else None}
        body = __import__("json").dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        print(encode_license(payload, ed25519.sign(secret, body)))
    else:
        pub = ed25519.public_key(bytes.fromhex(KEY_FILE.read_text().strip())).hex() if KEY_FILE.exists() else None
        print(verify_license(a.license, pub))


if __name__ == "__main__":
    main()
