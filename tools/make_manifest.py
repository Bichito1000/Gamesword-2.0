"""Genera update.json para el sistema de actualizaciones.

  python tools/make_manifest.py Gamesword-Setup-1.2.0.exe --version 1.2.0 --url https://tudominio.com/Gamesword-Setup-1.2.0.exe --notes "Novedades"

Sube el instalador y update.json a tu hosting (HTTPS) y pon la URL de update.json en Ajustes → Actualizaciones.
"""
import argparse
import hashlib
import json
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("installer")
ap.add_argument("--version", required=True)
ap.add_argument("--url", required=True)
ap.add_argument("--notes", default="")
ap.add_argument("--page", default="")
a = ap.parse_args()
sha = hashlib.sha256(Path(a.installer).read_bytes()).hexdigest()
Path("update.json").write_text(json.dumps(
    {"version": a.version, "url": a.url, "sha256": sha, "notes": a.notes, "page": a.page},
    indent=2, ensure_ascii=False), encoding="utf-8")
print("Creado update.json  (sha256:", sha, ")")
