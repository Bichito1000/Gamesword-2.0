"""Lanzadores de plataformas (Steam, Epic, Ubisoft, EA, GOG, Battle.net, Rockstar, Discord)."""
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Set, Tuple

import psutil

from utils.helpers import open_uri
from utils.logger import get_logger
from .game_detector import steam_root

log = get_logger("platforms")


@dataclass
class LauncherInfo:
    key: str
    name: str
    candidates: List[str] = field(default_factory=list)
    args: List[str] = field(default_factory=list)
    uri: str = ""                       # alternativa si no hay .exe
    processes: List[str] = field(default_factory=list)
    download_url: str = ""
    aliases: List[str] = field(default_factory=list)


PF = r"%ProgramFiles%"
PF86 = r"%ProgramFiles(x86)%"

LAUNCHERS: List[LauncherInfo] = [
    LauncherInfo("steam", "Steam", [], uri="steam://open/main", processes=["steam.exe"],
                 download_url="https://store.steampowered.com/about/", aliases=["steam"]),
    LauncherInfo("epic", "Epic Games",
                 [PF86 + r"\Epic Games\Launcher\Portal\Binaries\Win32\EpicGamesLauncher.exe",
                  PF86 + r"\Epic Games\Launcher\Portal\Binaries\Win64\EpicGamesLauncher.exe"],
                 uri="com.epicgames.launcher://", processes=["EpicGamesLauncher.exe"],
                 download_url="https://store.epicgames.com/download", aliases=["epic", "epic games", "epic launcher"]),
    LauncherInfo("ubisoft", "Ubisoft Connect",
                 [PF86 + r"\Ubisoft\Ubisoft Game Launcher\UbisoftConnect.exe",
                  PF86 + r"\Ubisoft\Ubisoft Game Launcher\upc.exe"],
                 uri="uplay://", processes=["UbisoftConnect.exe", "upc.exe"],
                 download_url="https://ubisoftconnect.com/", aliases=["ubisoft", "ubisoft connect", "uplay"]),
    LauncherInfo("ea", "EA app",
                 [PF + r"\Electronic Arts\EA Desktop\EA Desktop\EADesktop.exe"],
                 processes=["EADesktop.exe"], download_url="https://www.ea.com/ea-app",
                 aliases=["ea", "ea app", "origin", "ea desktop"]),
    LauncherInfo("gog", "GOG Galaxy", [PF86 + r"\GOG Galaxy\GalaxyClient.exe"],
                 processes=["GalaxyClient.exe"], download_url="https://www.gog.com/galaxy",
                 aliases=["gog", "gog galaxy", "galaxy"]),
    LauncherInfo("battlenet", "Battle.net", [PF86 + r"\Battle.net\Battle.net Launcher.exe"],
                 processes=["Battle.net.exe"], download_url="https://www.blizzard.com/download",
                 aliases=["battle net", "battlenet", "blizzard"]),
    LauncherInfo("rockstar", "Rockstar Launcher", [PF + r"\Rockstar Games\Launcher\Launcher.exe"],
                 processes=["Launcher.exe"],
                 download_url="https://socialclub.rockstargames.com/rockstar-games-launcher",
                 aliases=["rockstar", "rockstar launcher", "social club"]),
    LauncherInfo("discord", "Discord", [r"%LOCALAPPDATA%\Discord\Update.exe"],
                 args=["--processStart", "Discord.exe"], processes=["Discord.exe"],
                 download_url="https://discord.com/download", aliases=["discord"]),
]

LAUNCHERS_BY_KEY = {l.key: l for l in LAUNCHERS}


class PlatformManager:
    def __init__(self, settings):
        self.settings = settings

    # ---------------------------------------------------------------- rutas
    def custom_path(self, key: str) -> Optional[Path]:
        p = (self.settings.get("launchers.paths", {}) or {}).get(key)
        return Path(p) if p and Path(p).exists() else None

    def find_exe(self, key: str) -> Optional[Path]:
        info = LAUNCHERS_BY_KEY[key]
        custom = self.custom_path(key)
        if custom:
            return custom
        if key == "steam":
            root = steam_root()
            if root and (root / "steam.exe").exists():
                return root / "steam.exe"
        for cand in info.candidates:
            p = Path(os.path.expandvars(cand))
            if p.exists():
                return p
        return None

    def is_installed(self, key: str) -> bool:
        return self.find_exe(key) is not None

    def installed_keys(self) -> List[str]:
        return [l.key for l in LAUNCHERS if self.is_installed(l.key)]

    def set_custom_path(self, key: str, path: str) -> None:
        paths = dict(self.settings.get("launchers.paths", {}) or {})
        paths[key] = path
        self.settings.set("launchers.paths", paths)

    # ------------------------------------------------------------ ejecución
    def running_keys(self) -> Set[str]:
        names = set()
        for p in psutil.process_iter(["name"]):
            try:
                names.add((p.info["name"] or "").lower())
            except (psutil.Error, OSError):
                continue
        return {l.key for l in LAUNCHERS if any(pn.lower() in names for pn in l.processes)}

    def open(self, key: str) -> Tuple[bool, str]:
        info = LAUNCHERS_BY_KEY[key]
        exe = self.find_exe(key)
        try:
            if exe:
                subprocess.Popen([str(exe), *info.args], cwd=str(exe.parent))
                return True, f"Abriendo {info.name}…"
            if info.uri:
                open_uri(info.uri)
                return True, f"Abriendo {info.name}…"
        except OSError as exc:
            log.warning("No se pudo abrir %s: %s", info.name, exc)
            return False, f"No se pudo abrir {info.name}: {exc}"
        return False, f"{info.name} no está instalado (o no se encontró su ruta)."

    # --------------------------------------------------------- alias → clave
    def resolve_alias(self, text: str) -> Optional[str]:
        from utils.helpers import normalize
        t = normalize(text)
        for l in LAUNCHERS:
            if t == normalize(l.name) or t in [normalize(a) for a in l.aliases]:
                return l.key
        return None
