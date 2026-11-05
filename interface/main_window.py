"""Ventana principal: barra lateral con iconos, páginas, bandeja, atajos globales, mando y actualizaciones."""
import time

from PySide6.QtCore import QEasingCurve, QEvent, QPropertyAnimation, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QKeyEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import (QAbstractButton, QApplication, QButtonGroup, QFrame, QGraphicsOpacityEffect,
                               QHBoxLayout, QLabel, QListWidget, QMainWindow, QMenu, QMessageBox, QPushButton,
                               QStackedWidget, QSystemTrayIcon, QVBoxLayout, QWidget)

from ai.voice import VoiceError
from config.settings import VERSION
from core import telemetry, updater
from core.gamepad import GamepadPoller
from core.hotkeys import HotkeyManager
from utils.helpers import format_clock
from utils.logger import get_logger
from utils.qt_async import call_in_main, run_async
from . import theme
from .ai_chat_view import AIChatView
from .dashboard_view import DashboardView
from .discover_view import DiscoverView
from .friends_view import FriendsView
from .icons import nav_icon
from .launcher_view import LauncherView
from .library_view import LibraryView
from .performance_view import PerformanceView
from .profile_view import ProfileView
from .settings_view import SettingsView
from .stats_view import StatsView
from .widgets import LogoWidget, app_icon, muted

log = get_logger("window")

# (texto, icono, vista, función de licencia que exige)
PAGES = [("Inicio", "home", DashboardView, None), ("Biblioteca", "library", LibraryView, None),
         ("Lanzadores", "launch", LauncherView, None), ("Gamesword AI", "ai", AIChatView, None),
         ("Estadísticas", "stats", StatsView, None), ("Rendimiento", "perf", PerformanceView, "performance"),
         ("Amigos", "friends", FriendsView, None), ("Descubrir", "discover", DiscoverView, None),
         ("Perfil", "profile", ProfileView, None), ("Ajustes", "settings", SettingsView, None)]
IDX = {cls.__name__: i for i, (_, _, cls, _) in enumerate(PAGES)}


class MainWindow(QMainWindow):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self._quitting = False
        self._tray_hint_shown = False
        self._anim = None
        self.setWindowTitle("GAMESWORD — Todos tus juegos. Una sola experiencia.")
        self.setWindowIcon(app_icon())
        self.setMinimumSize(1180, 760)
        self.resize(1360, 840)

        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        side = QFrame()
        side.setObjectName("Sidebar")
        self.sidebar = side
        side.setFixedWidth(190 if ctx.settings.get("app.compact") else 232)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(0, 8, 0, 14)
        sl.setSpacing(2)
        sl.addWidget(LogoWidget())
        sl.addSpacing(10)

        self.stack = QStackedWidget()
        self.views, self.nav_buttons = [], []
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        for i, (text, icon, cls, _) in enumerate(PAGES):
            btn = QPushButton("  " + text)
            btn.setObjectName("NavButton")
            btn.setCheckable(True)
            btn.setIcon(nav_icon(icon))
            btn.setIconSize(QSize(20, 20))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self.group.addButton(btn, i)
            sl.addWidget(btn)
            self.nav_buttons.append(btn)
            view = cls(ctx)
            view.message.connect(self.show_message)
            self.views.append(view)
            self.stack.addWidget(view)
            QShortcut(QKeySequence(f"Ctrl+{i + 1}"), self, activated=lambda idx=i: self.go(idx))
        sl.addStretch()
        self.now_playing = QLabel("")
        self.now_playing.setObjectName("Success")
        self.now_playing.setWordWrap(True)
        self.now_playing.setContentsMargins(20, 0, 20, 0)
        sl.addWidget(self.now_playing)
        ver = muted("v" + VERSION, wrap=False)
        ver.setContentsMargins(20, 6, 0, 0)
        sl.addWidget(ver)

        h.addWidget(side)
        h.addWidget(self.stack, 1)
        self.group.idClicked.connect(self.go)

        settings_view = self.view(SettingsView)
        settings_view.theme_changed = self.change_theme
        settings_view.on_saved = self.apply_runtime_settings
        settings_view.check_updates = self.check_updates
        settings_view.on_restored = lambda: self.views[self.stack.currentIndex()].refresh()
        self.status = self.statusBar()
        self.status.setSizeGripEnabled(False)

        t = ctx.tracker
        t.session_started.connect(self._on_started)
        t.session_tick.connect(self._on_tick)
        t.session_finished.connect(self._on_finished)
        t.notice.connect(self.show_message)
        t.launched.connect(self._on_launched)
        ctx.progress.on_unlock = lambda unlocks: call_in_main(lambda: self._unlocks(unlocks))

        self._build_tray()
        self.hotkeys = HotkeyManager()
        self.hotkeys.triggered.connect(self._hotkey)
        self.pad = GamepadPoller()
        self.pad.action.connect(self._pad)

        self.heartbeat = QTimer(self)
        self.heartbeat.setInterval(30_000)
        self.heartbeat.timeout.connect(self._beat)
        self.heartbeat.start()

        self.group.button(0).setChecked(True)
        self.go(0)
        self.apply_runtime_settings()

    def view(self, cls):
        return self.views[IDX[cls.__name__]]

    # ---------------------------------------------------------------- páginas
    def go(self, index: int) -> None:
        index %= len(PAGES)
        need = PAGES[index][3]
        if need and not self.ctx.license.allows(need):
            self.show_message(f"«{PAGES[index][0]}» requiere una licencia Pro. Actívala en Ajustes → Licencia.")
            self.group.button(self.stack.currentIndex()).setChecked(True)
            return
        self.group.button(index).setChecked(True)
        self.stack.setCurrentIndex(index)
        view = self.views[index]
        view.refresh()
        self._fade(view)

    def _fade(self, widget: QWidget) -> None:
        """Aparición suave de la página (se omite si algo falla; es solo estética)."""
        try:
            eff = QGraphicsOpacityEffect(widget)
            widget.setGraphicsEffect(eff)
            anim = QPropertyAnimation(eff, b"opacity", self)
            anim.setDuration(200)
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            anim.finished.connect(lambda w=widget: w.setGraphicsEffect(None))
            anim.start()
            self._anim = anim
        except Exception:  # noqa: BLE001
            log.debug("Animación omitida", exc_info=True)

    def show_message(self, text: str) -> None:
        self.status.showMessage(text, 7000)

    def change_theme(self, key: str = "") -> None:
        """Reaplica tema, colores y modo compacto desde los ajustes."""
        theme.apply_from_settings(QApplication.instance(), self.ctx.settings)
        self.sidebar.setFixedWidth(190 if self.ctx.settings.get("app.compact") else 232)
        library = self.view(LibraryView)
        library.apply_compact()
        for btn, (_, icon, _, _) in zip(self.nav_buttons, PAGES):
            btn.setIcon(nav_icon(icon))
        for v in self.views:
            v.update()
        self.views[self.stack.currentIndex()].refresh()
        self.centralWidget().update()

    # ----------------------------------------------------------------- bandeja
    def _build_tray(self) -> None:
        self.tray = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(app_icon(), self)
        self.tray.setToolTip("Gamesword")
        menu = QMenu()
        act_open = QAction("Abrir Gamesword", self)
        act_open.triggered.connect(self.show_window)
        act_ai = QAction("Gamesword AI", self)
        act_ai.triggered.connect(lambda: (self.show_window(), self.go(IDX["AIChatView"])))
        act_voice = QAction("Hablar con la IA  (Ctrl+Alt+V)", self)
        act_voice.triggered.connect(lambda: self._hotkey("voice"))
        act_quit = QAction("Salir", self)
        act_quit.triggered.connect(self.quit_app)
        for a in (act_open, act_ai, act_voice):
            menu.addAction(a)
        menu.addSeparator()
        menu.addAction(act_quit)
        self._tray_menu = menu          # evita que Python lo libere
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self.toggle_window()
                                    if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
        self.tray.show()

    def show_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def toggle_window(self) -> None:
        if self.isVisible() and not self.isMinimized() and self.isActiveWindow():
            self.hide()
        else:
            self.show_window()

    def quit_app(self) -> None:
        self._quitting = True
        self.close()
        QApplication.quit()

    def tray_notify(self, title: str, text: str) -> None:
        if self.tray is not None:
            self.tray.showMessage(title, text, QSystemTrayIcon.MessageIcon.Information, 5000)

    # ------------------------------------------------------ ajustes en caliente
    def apply_runtime_settings(self) -> None:
        s, lic = self.ctx.settings, self.ctx.license
        if s.get("app.hotkeys", True):
            self.hotkeys.start()
        else:
            self.hotkeys.stop()
        if s.get("app.gamepad", True) and lic.allows("gamepad"):
            self.pad.start()
        else:
            self.pad.stop()
        voice = self.ctx.voice
        if s.get("voice.wake_word") and lic.allows("wake_word"):
            try:
                voice.start_wake(self._wake_heard)
                self.show_message("Escuchando «Oye Gamesword»…")
            except VoiceError as exc:
                self.show_message(str(exc))
        else:
            voice.stop_wake()

    # ------------------------------------------------------------------ atajos
    def _hotkey(self, action: str) -> None:
        if action == "toggle":
            self.toggle_window()
        elif action == "voice":
            self.show_window()
            self.go(IDX["AIChatView"])
            self.view(AIChatView).listen_now()

    def _wake_heard(self, text: str) -> None:       # hilo de escucha -> hilo de la interfaz
        call_in_main(lambda: self._on_wake(text))

    def _on_wake(self, text: str) -> None:
        self.tray_notify("Gamesword AI", f"Te he oído: {text}")
        self.view(AIChatView).send(text, speak=True)

    # -------------------------------------------------------------------- mando
    def _pad(self, action: str) -> None:
        modal = QApplication.activeModalWidget()
        if QApplication.activeWindow() is None and modal is None:
            return                                    # el mando está en uso por un juego: no interferir
        cur = self.stack.currentIndex()
        if action in ("prev", "next") and modal is None:
            self.go(cur + (1 if action == "next" else -1))
            return
        if action == "menu" and modal is None:
            self.go(IDX["AIChatView"])
            return
        if action == "back":
            if modal is not None:
                self._send_key(modal, Qt.Key.Key_Escape)
            elif cur != 0:
                self.go(0)
            return
        w = QApplication.focusWidget()
        if w is None:
            view = self.stack.currentWidget()
            w = view.findChild(QListWidget) or view
            w.setFocus()
        keys = {"up": Qt.Key.Key_Up, "down": Qt.Key.Key_Down, "left": Qt.Key.Key_Left, "right": Qt.Key.Key_Right,
                "tab": Qt.Key.Key_Tab, "backtab": Qt.Key.Key_Backtab}
        if action == "accept":
            self._send_key(w, Qt.Key.Key_Space if isinstance(w, QAbstractButton) else Qt.Key.Key_Return)
        elif action in keys:
            self._send_key(w, keys[action])

    @staticmethod
    def _send_key(widget, key) -> None:
        mod = Qt.KeyboardModifier.ShiftModifier if key == Qt.Key.Key_Backtab else Qt.KeyboardModifier.NoModifier
        for kind in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            QApplication.sendEvent(widget, QKeyEvent(kind, key, mod))

    # ------------------------------------------------------------ seguimiento
    def _on_started(self, _gid: int, name: str) -> None:
        self.now_playing.setText(f"● Jugando a\n{name}")
        self.show_message(f"Registrando tu tiempo en {name}")
        self.ctx.presence.set_playing(name, time.time())
        if self.ctx.settings.get("app.minimize_on_game_launch"):
            self.showMinimized()
        self._beat()

    def _on_launched(self, gid: int, name: str) -> None:
        self.ctx.progress.log_activity("launch", f"Abriste {name}", 0, str(gid))
        run_async(self.ctx.progress.record, None, None, "launches")

    def _unlocks(self, unlocks) -> None:
        for u in unlocks:
            kind = "Logro desbloqueado" if u.kind == "achievement" else "Desafío completado"
            self.show_message(f"🏆 {kind}: {u.name}  (+{u.xp} XP)")
            self.tray_notify(kind, f"{u.name}  ·  +{u.xp} XP")
        current = self.views[self.stack.currentIndex()]
        if isinstance(current, (ProfileView, StatsView)):
            current.refresh()

    def _on_tick(self, _gid: int, name: str, seconds: int) -> None:
        self.now_playing.setText(f"● Jugando a\n{name}\n{format_clock(seconds)}")

    def _on_finished(self, _gid: int, name: str, seconds: int) -> None:
        if not self.ctx.tracker.active():
            self.now_playing.setText("")
            self.ctx.presence.clear()
        if seconds >= 15:
            self.ctx.progress.log_activity("play", f"Jugaste {max(1, seconds // 60)} min a {name}", 0, str(_gid))
            run_async(self.ctx.progress.evaluate)
            m = seconds // 60
            msg = f"Sesión de {name} guardada: {m} min." if m else f"Sesión de {name} guardada."
            self.show_message(msg)
            self.tray_notify("Gamesword", msg)
        self._beat()

    def _beat(self) -> None:
        s = self.ctx.social
        if s.enabled:
            run_async(s.ping, self._invites, None, self.ctx.tracker.current_game_name())

    def _invites(self, invites) -> None:
        for inv in invites or []:
            game = f" a {inv['game']}" if inv.get("game") else ""
            text = f"{inv['from_name']} te invita a jugar{game}" + (f": «{inv['note']}»" if inv.get("note") else "")
            self.show_message("🎮 " + text)
            self.tray_notify("Invitación de Gamesword", text)

    # ----------------------------------------------------------- actualizaciones
    def check_updates(self, manual: bool = False) -> None:
        url = (self.ctx.settings.get("app.update_url", "") or "").strip()
        if not url:
            if manual:
                self.show_message("Indica primero la dirección del manifiesto de actualizaciones.")
            return
        run_async(updater.check, lambda info: self._update_found(info, manual),
                  lambda e: self.show_message(str(e)) if manual else log.info("Actualizaciones: %s", e),
                  url, VERSION)

    def _update_found(self, info, manual: bool) -> None:
        if info is None:
            if manual:
                self.show_message(f"Gamesword {VERSION} está al día.")
            return
        notes = f"\n\n{info.notes}" if info.notes else ""
        if updater.can_self_install():
            ask = QMessageBox.question(self, "Actualización disponible",
                                       f"Hay una versión nueva: {info.version} (tienes {VERSION}).{notes}\n\n"
                                       "¿Descargar e instalar ahora? Gamesword se cerrará y se reabrirá.")
            if ask == QMessageBox.StandardButton.Yes:
                self.show_message("Descargando actualización…")
                run_async(updater.download, self._install_update, lambda e: self.show_message(str(e)), info)
        else:
            ask = QMessageBox.question(self, "Actualización disponible",
                                       f"Hay una versión nueva: {info.version} (tienes {VERSION}).{notes}\n\n"
                                       "¿Abrir la página de descarga?")
            if ask == QMessageBox.StandardButton.Yes:
                updater.open_page(info)

    def _install_update(self, path) -> None:
        updater.install(path)
        self.quit_app()

    # ------------------------------------------------------------------ cierre
    def closeEvent(self, event) -> None:
        if (self.ctx.settings.get("app.close_to_tray") and self.tray is not None and not self._quitting):
            event.ignore()
            self.hide()
            if not self._tray_hint_shown:
                self._tray_hint_shown = True
                self.tray_notify("Gamesword sigue abierto", "Ábrelo desde el icono de la bandeja o con Ctrl+Alt+G.")
            return
        self.hotkeys.stop()
        self.pad.stop()
        self.ctx.voice.stop_wake()
        self.ctx.voice.stop()
        self.ctx.presence.close()
        self.ctx.tracker.stop_all()
        self.ctx.covers.shutdown()
        if self.tray is not None:
            self.tray.hide()
        super().closeEvent(event)
