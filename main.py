"""
GAMESWORD — Todos tus juegos. Una sola experiencia.
Centro gaming para Windows 10/11 · Python + PySide6 + SQLite

Ejecuta:  python main.py            (python main.py --minimized  para arrancar en la bandeja)
"""
import sys
import traceback
from pathlib import Path

# Permite ejecutar desde cualquier carpeta
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from ai.assistant import GamesAssistant
from ai.voice import VoiceEngine
from config.settings import VERSION, load_settings
from core import backup, diagnostics, telemetry
from core.context import AppContext
from core.covers import CoverFetcher
from core.database import DatabaseManager
from core.game_tracker import GameTracker
from core.licensing import LicenseManager
from core.platform_manager import PlatformManager
from core.progress import ProgressManager
from core.rich_presence import RichPresence
from core.social import SocialClient
from interface import theme
from interface.main_window import IDX, MainWindow
from interface.library_view import LibraryView
from interface.widgets import app_icon
from utils.logger import setup_logger
from utils.qt_async import call_in_main, init_async


def build_context():
    settings = load_settings()
    settings.set("app.version", VERSION, save=False)
    db = DatabaseManager()
    notice = backup.recover_if_corrupt(db.path)       # si la base estaba dañada, restaura la última copia buena
    db.init()
    if backup.backup_due(settings):
        try:
            backup.create_backup(db.path, settings, VERSION)
        except backup.BackupError:
            pass
    platforms = PlatformManager(settings)
    tracker = GameTracker(db, settings)
    ctx = AppContext(settings=settings, db=db, platforms=platforms, tracker=tracker,
                     covers=CoverFetcher(db, settings), social=SocialClient(settings),
                     license=LicenseManager(settings), presence=RichPresence(settings),
                     progress=ProgressManager(db, settings))
    ctx.voice = VoiceEngine(settings)
    ctx.assistant = GamesAssistant(db, settings, tracker, platforms)
    ctx.assistant.license = ctx.license
    ctx.assistant.progress = ctx.progress
    return ctx, notice


def main() -> int:
    logger = setup_logger()
    state = {"ctx": None, "reported": False}

    def excepthook(exc_type, exc, tb):
        logger.error("Excepción no controlada:\n%s", "".join(traceback.format_exception(exc_type, exc, tb)))
        if state["reported"] or state["ctx"] is None:
            return
        state["reported"] = True

        def ask():
            box = QMessageBox.question(
                None, "Gamesword", "Ha ocurrido un error inesperado. La aplicación puede seguir funcionando.\n\n"
                "¿Quieres crear un informe de diagnóstico (sin tus claves) para pedir ayuda?")
            if box == QMessageBox.StandardButton.Yes:
                from utils.helpers import open_in_explorer
                open_in_explorer(diagnostics.create_report(state["ctx"].settings, state["ctx"]))
        try:
            call_in_main(ask)
        except Exception:  # noqa: BLE001
            pass
    sys.excepthook = excepthook

    app = QApplication(sys.argv)
    app.setApplicationName("Gamesword")
    app.setOrganizationName("Gamesword")
    app.setApplicationVersion(VERSION)
    app.setStyle("Fusion")
    app.setWindowIcon(app_icon())
    init_async()

    try:
        ctx, notice = build_context()
        state["ctx"] = ctx
        theme.apply_from_settings(app, ctx.settings)
        window = MainWindow(ctx)
    except Exception as exc:  # noqa: BLE001
        logger.exception("No se pudo iniciar Gamesword")
        QMessageBox.critical(None, "Gamesword", f"No se pudo iniciar la aplicación:\n\n{exc}\n\n"
                                                "Consulta logs/gamesword.log para más detalles.")
        return 1

    if notice:
        QMessageBox.warning(window, "Gamesword", notice)
    start_hidden = ("--minimized" in sys.argv or ctx.settings.get("app.start_minimized")) and window.tray is not None
    if start_hidden:
        window.tray_notify("Gamesword", "Gamesword está en la bandeja. Ctrl+Alt+G lo abre.")
    else:
        window.show()
    logger.info("Gamesword %s iniciado", VERSION)

    if ctx.settings.get("app.auto_scan_on_start", True):
        QTimer.singleShot(800, lambda: window.view(LibraryView).scan(True))
    if ctx.social.enabled:
        QTimer.singleShot(1500, window._beat)
    telemetry.send_event(ctx.settings, "start")
    if ctx.settings.get("app.check_updates", True) and ctx.settings.get("app.update_url"):
        QTimer.singleShot(4000, lambda: window.check_updates(False))

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
