"""Contenedor de servicios compartidos por toda la aplicación."""
from dataclasses import dataclass

from config.settings import Settings
from core.covers import CoverFetcher
from core.database import DatabaseManager
from core.game_tracker import GameTracker
from core.licensing import LicenseManager
from core.platform_manager import PlatformManager
from core.progress import ProgressManager
from core.rich_presence import RichPresence
from core.social import SocialClient


@dataclass
class AppContext:
    settings: Settings
    db: DatabaseManager
    platforms: PlatformManager
    tracker: GameTracker
    covers: CoverFetcher
    social: SocialClient
    progress: ProgressManager = None
    license: LicenseManager = None
    presence: RichPresence = None
    voice: object = None       # ai.voice.VoiceEngine
    assistant: object = None   # ai.assistant.GamesAssistant
