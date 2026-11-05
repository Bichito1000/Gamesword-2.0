"""Construye Gamesword.exe con PyInstaller. Lo usan CREAR_EXE.bat y GitHub Actions (misma receta).

  python tools/build_exe.py            # compila
  python tools/build_exe.py --dry-run  # solo muestra el comando
"""
import argparse
import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def have(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


def command() -> list:
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--name", "Gamesword",
           "--collect-submodules", "pyttsx3", "--hidden-import", "pyttsx3.drivers.sapi5", "--hidden-import", "comtypes",
           "--collect-submodules", "keyring", "--hidden-import", "keyring.backends.Windows"]
    icon = ROOT / "resources" / "gamesword.ico"
    if icon.exists():
        cmd += ["--icon", str(icon)]
    # Opcionales: solo se incluyen si están instalados en el entorno de compilación
    if have("speech_recognition"):
        cmd += ["--collect-all", "speech_recognition"]
    if have("pypresence"):
        cmd += ["--hidden-import", "pypresence"]
    if have("faster_whisper"):
        cmd += ["--collect-all", "faster_whisper"]
    cmd.append(str(ROOT / "main.py"))
    return cmd


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    cmd = command()
    print(" ".join(f'"{c}"' if " " in c else c for c in cmd))
    if args.dry_run:
        return 0
    if not have("PyInstaller"):
        print("Falta PyInstaller:  pip install pyinstaller")
        return 1
    return subprocess.call(cmd, cwd=str(ROOT))


if __name__ == "__main__":
    sys.exit(main())
