"""Detección de juegos instalados: Steam, Epic, Ubisoft Connect, GOG y EA, más carpetas propias."""
import json
import os
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path
from typing import List, Optional

from utils.helpers import normalize
from utils.logger import get_logger
from .models import DetectedGame

log = get_logger("detector")

try:
    import winreg  # type: ignore
except ImportError:  # Linux/macOS (solo para pruebas)
    winreg = None

_BAD_EXE = ("unins", "crash", "redist", "setup", "vcredist", "vc_redist", "dxsetup", "cleanup",
            "touchup", "activation", "anticheat", "easyanticheat", "battleye", "uninstall",
            "dotnet", "directx", "support", "report", "updater", "helper", "eadm")


# --------------------------------------------------------------- utilidades
def _reg_value(hive, key: str, value: str) -> Optional[str]:
    if winreg is None:
        return None
    try:
        with winreg.OpenKey(hive, key) as k:
            return str(winreg.QueryValueEx(k, value)[0])
    except OSError:
        return None


def _reg_subkeys(hive, key: str) -> List[str]:
    if winreg is None:
        return []
    names = []
    try:
        with winreg.OpenKey(hive, key) as k:
            i = 0
            while True:
                try:
                    names.append(winreg.EnumKey(k, i))
                    i += 1
                except OSError:
                    break
    except OSError:
        pass
    return names


def guess_exe(folder: Path, name: str = "") -> str:
    """Elige el .exe más probable de un juego dentro de su carpeta."""
    folder = Path(folder)
    if not folder.is_dir():
        return ""
    candidates = []
    try:
        candidates = list(folder.glob("*.exe")) + list(folder.glob("*/*.exe"))
    except OSError:
        return ""
    target = normalize(name or folder.name).replace(" ", "")
    best, best_score = "", -1.0
    for exe in candidates:
        stem = exe.stem.lower()
        if any(bad in stem for bad in _BAD_EXE):
            continue
        ratio = SequenceMatcher(None, normalize(exe.stem).replace(" ", ""), target).ratio()
        try:
            size_bonus = min(exe.stat().st_size / 500_000_000, 0.3)
        except OSError:
            size_bonus = 0
        depth_penalty = 0.05 if exe.parent != folder else 0
        score = ratio + size_bonus - depth_penalty
        if score > best_score:
            best, best_score = str(exe), score
    return best


def _clean_path(value: str) -> str:
    return value.strip().strip('"').rstrip("\\/")


# -------------------------------------------------------------------- Steam
def steam_root() -> Optional[Path]:
    if winreg is not None:
        for hive, key, val in (
            (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", "InstallPath"),
        ):
            v = _reg_value(hive, key, val)
            if v and Path(v).exists():
                return Path(v)
    for env in ("ProgramFiles(x86)", "ProgramFiles"):
        base = os.environ.get(env)
        if base and (Path(base) / "Steam").exists():
            return Path(base) / "Steam"
    return None


def steam_user_id() -> Optional[str]:
    """SteamID64 de la cuenta usada más recientemente en este PC (loginusers.vdf)."""
    root = steam_root()
    if not root:
        return None
    try:
        text = (root / "config" / "loginusers.vdf").read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    best = None
    for m in re.finditer(r'"(\d{17})"\s*\{(.*?)\}', text, re.S):
        if best is None:
            best = m.group(1)
        if re.search(r'"MostRecent"\s+"1"', m.group(2)):
            return m.group(1)
    return best


def _steam_libraries(root: Path) -> List[Path]:
    libs = [root / "steamapps"]
    vdf = root / "steamapps" / "libraryfolders.vdf"
    try:
        text = vdf.read_text(encoding="utf-8", errors="ignore")
        for m in re.finditer(r'"path"\s+"([^"]+)"', text):
            p = Path(m.group(1).replace("\\\\", "\\")) / "steamapps"
            if p not in libs and p.exists():
                libs.append(p)
    except OSError:
        pass
    return libs


def detect_steam() -> List[DetectedGame]:
    root = steam_root()
    if not root:
        return []
    out = []
    for lib in _steam_libraries(root):
        for acf in lib.glob("appmanifest_*.acf"):
            try:
                data = dict(re.findall(r'"(\w+)"\s+"([^"]*)"', acf.read_text(encoding="utf-8", errors="ignore")))
            except OSError:
                continue
            appid, name = data.get("appid", ""), data.get("name", "")
            if not appid or not name or appid == "228980":
                continue
            if any(x in name.lower() for x in ("steamworks", "proton ", "steam linux runtime", "redistributable")):
                continue
            install = lib / "common" / data.get("installdir", "")
            out.append(DetectedGame(
                name=name, platform="steam", external_id=appid,
                launch_uri=f"steam://rungameid/{appid}",
                install_dir=str(install) if install.exists() else "",
            ))
    return out


# --------------------------------------------------------------------- Epic
def detect_epic() -> List[DetectedGame]:
    base = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests"
    if not base.exists():
        return []
    out = []
    for item in base.glob("*.item"):
        try:
            d = json.loads(item.read_text(encoding="utf-8", errors="ignore"))
        except (OSError, json.JSONDecodeError):
            continue
        name, app = d.get("DisplayName"), d.get("AppName")
        if not name or not app or d.get("bIsIncompleteInstall"):
            continue
        main = d.get("MainGameAppName")
        if main and main != app:      # DLC
            continue
        launch_exe = d.get("LaunchExecutable", "")
        out.append(DetectedGame(
            name=name, platform="epic", external_id=app,
            launch_uri=f"com.epicgames.launcher://apps/{app}?action=launch&silent=true",
            install_dir=d.get("InstallLocation", ""),
            process_name=Path(launch_exe).name if launch_exe else "",
        ))
    return out


# ------------------------------------------------------------------ Ubisoft
def detect_ubisoft() -> List[DetectedGame]:
    if winreg is None:
        return []
    key = r"SOFTWARE\WOW6432Node\Ubisoft\Launcher\Installs"
    out = []
    for sub in _reg_subkeys(winreg.HKEY_LOCAL_MACHINE, key):
        d = _reg_value(winreg.HKEY_LOCAL_MACHINE, f"{key}\\{sub}", "InstallDir")
        if not d:
            continue
        d = _clean_path(d)
        if not Path(d).exists():
            continue
        out.append(DetectedGame(
            name=Path(d).name, platform="ubisoft", external_id=sub,
            launch_uri=f"uplay://launch/{sub}/0", install_dir=d))
    return out


# ---------------------------------------------------------------------- GOG
def detect_gog() -> List[DetectedGame]:
    if winreg is None:
        return []
    key = r"SOFTWARE\WOW6432Node\GOG.com\Games"
    out = []
    for sub in _reg_subkeys(winreg.HKEY_LOCAL_MACHINE, key):
        k = f"{key}\\{sub}"
        name = _reg_value(winreg.HKEY_LOCAL_MACHINE, k, "gameName")
        exe = _reg_value(winreg.HKEY_LOCAL_MACHINE, k, "exe")
        path = _reg_value(winreg.HKEY_LOCAL_MACHINE, k, "path")
        if name and exe:
            out.append(DetectedGame(name=name, platform="gog", external_id=sub, exe_path=exe,
                                    install_dir=path or str(Path(exe).parent),
                                    process_name=Path(exe).name))
    return out


# ----------------------------------------------------------------------- EA
def detect_ea() -> List[DetectedGame]:
    folders = set()
    if winreg is not None:
        key = r"SOFTWARE\WOW6432Node\EA Games"
        for sub in _reg_subkeys(winreg.HKEY_LOCAL_MACHINE, key):
            for val in ("Install Dir", "InstallDir"):
                v = _reg_value(winreg.HKEY_LOCAL_MACHINE, f"{key}\\{sub}", val)
                if v and Path(_clean_path(v)).is_dir():
                    folders.add(Path(_clean_path(v)))
    for env in ("ProgramFiles", "ProgramFiles(x86)"):
        base = os.environ.get(env)
        if not base:
            continue
        for sub in ("EA Games", "Electronic Arts"):
            root = Path(base) / sub
            if root.is_dir():
                folders.update(p for p in root.iterdir() if p.is_dir() and p.name != "EA Desktop")
    out = []
    for f in sorted(folders):
        exe = guess_exe(f, f.name)
        if exe:
            out.append(DetectedGame(name=f.name, platform="ea", external_id=f"ea:{normalize(f.name)}",
                                    exe_path=exe, install_dir=str(f), process_name=Path(exe).name))
    return out


# ------------------------------------------------------- Xbox / Game Pass (PC)
def _drive_roots() -> List[Path]:
    roots = []
    if sys.platform == "win32":
        for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ":
            r = Path(f"{letter}:\\")
            try:
                if r.exists():
                    roots.append(r)
            except OSError:
                continue
    return roots


def detect_xbox() -> List[DetectedGame]:
    """Juegos de Xbox app / Game Pass instalados en <unidad>:\\XboxGames\\<Juego>\\Content."""
    out = []
    for root in _drive_roots():
        base = root / "XboxGames"
        if not base.is_dir():
            continue
        for game_dir in sorted(p for p in base.iterdir() if p.is_dir()):
            content = game_dir / "Content"
            exe = guess_exe(content if content.is_dir() else game_dir, game_dir.name)
            if exe:
                out.append(DetectedGame(name=game_dir.name, platform="xbox",
                                        external_id=f"xbox:{normalize(game_dir.name)}", exe_path=exe,
                                        install_dir=str(game_dir), process_name=Path(exe).name))
    return out


# ------------------------------------- Battle.net / Rockstar (por registro de Windows)
_UNINSTALL_KEYS = (r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
                   r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall")
_PUBLISHERS = {"blizzard entertainment": "battlenet", "rockstar games": "rockstar"}
_SKIP_NAMES = ("battle.net", "launcher", "social club", "redistributable", "runtime")


def detect_by_publisher() -> List[DetectedGame]:
    if winreg is None:
        return []
    out = []
    for key in _UNINSTALL_KEYS:
        for sub in _reg_subkeys(winreg.HKEY_LOCAL_MACHINE, key):
            k = f"{key}\\{sub}"
            pub = (_reg_value(winreg.HKEY_LOCAL_MACHINE, k, "Publisher") or "").lower()
            platform = _PUBLISHERS.get(pub)
            if not platform:
                continue
            name = _reg_value(winreg.HKEY_LOCAL_MACHINE, k, "DisplayName") or ""
            loc = _reg_value(winreg.HKEY_LOCAL_MACHINE, k, "InstallLocation") or ""
            if not name or any(x in name.lower() for x in _SKIP_NAMES):
                continue
            loc = _clean_path(loc)
            exe = guess_exe(Path(loc), name) if loc else ""
            if exe:
                out.append(DetectedGame(name=name, platform=platform, external_id=f"{platform}:{normalize(name)}",
                                        exe_path=exe, install_dir=loc, process_name=Path(exe).name))
    return out


# ------------------------------------------------------------ carpeta propia
def scan_folder(folder: str, platform: str = "other") -> List[DetectedGame]:
    """Cada subcarpeta de `folder` se considera un juego (si contiene un .exe razonable)."""
    root = Path(folder)
    out = []
    if not root.is_dir():
        return out
    for sub in sorted(p for p in root.iterdir() if p.is_dir()):
        exe = guess_exe(sub, sub.name)
        if exe:
            out.append(DetectedGame(name=sub.name, platform=platform,
                                    external_id=f"folder:{normalize(str(sub))}",
                                    exe_path=exe, install_dir=str(sub), process_name=Path(exe).name))
    return out


def detect_all() -> List[DetectedGame]:
    results: List[DetectedGame] = []
    for fn in (detect_steam, detect_epic, detect_ubisoft, detect_gog, detect_ea, detect_xbox, detect_by_publisher):
        try:
            found = fn()
            log.info("%s: %d juegos", fn.__name__, len(found))
            results.extend(found)
        except Exception:
            log.exception("Fallo en %s", fn.__name__)
    return results
