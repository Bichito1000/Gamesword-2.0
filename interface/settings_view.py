"""Ajustes: apariencia, sistema, biblioteca, IA, voz, online, actualizaciones, licencia y diagnóstico."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QLineEdit, QMessageBox,
                               QPlainTextEdit, QPushButton, QScrollArea, QSlider, QVBoxLayout, QWidget)

from config.settings import VERSION
from pathlib import Path

from core import autostart, backup, diagnostics, licensing
from core.hotkeys import LABELS as HOTKEY_LABELS
from core.steam_import import SteamImportError, import_playtime
from utils.helpers import open_in_explorer
from utils.paths import data_dir
from utils.qt_async import run_async
from . import theme
from .dialogs import CustomCommandsDialog, MemoryDialog
from .widgets import BaseView, card_frame, h1, h2, muted, primary

PROVIDERS = [
    ("openai", "OpenAI", "https://api.openai.com/v1", "gpt-4o-mini"),
    ("openrouter", "OpenRouter", "https://openrouter.ai/api/v1", "openai/gpt-4o-mini"),
    ("groq", "Groq", "https://api.groq.com/openai/v1", "llama-3.3-70b-versatile"),
    ("ollama", "Ollama (local, sin clave)", "http://localhost:11434/v1", "llama3.1"),
    ("custom", "Personalizado (compatible OpenAI)", "", ""),
]
LANGS = [("es-ES", "Español (España)"), ("es-MX", "Español (México)"), ("es-AR", "Español (Argentina)"),
         ("en-US", "English (US)"), ("ca-ES", "Català"), ("fr-FR", "Français"), ("de-DE", "Deutsch"),
         ("it-IT", "Italiano"), ("pt-BR", "Português (Brasil)")]


class SettingsView(BaseView):
    theme_changed = None      # callables que asigna la ventana principal
    on_saved = None
    check_updates = None
    on_restored = None

    def __init__(self, ctx):
        super().__init__(ctx)
        s = ctx.settings
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(16)
        lay.addWidget(h1("Ajustes"))

        # ---- Apariencia
        self.theme = QComboBox()
        for key, t in theme.THEMES.items():
            self.theme.addItem(t["name"], key)
        self.theme.setCurrentIndex(max(0, self.theme.findData(s.get("app.theme"))))
        self.theme.currentIndexChanged.connect(self._apply_theme)
        self.compact = QCheckBox("Modo compacto (textos y portadas más pequeños, para pantallas o PCs justos)")
        self.compact.setChecked(bool(s.get("app.compact")))
        self.compact.toggled.connect(self._appearance_changed)
        accent_btn = QPushButton("Color principal…")
        accent_btn.clicked.connect(lambda: self._pick_color("app.accent"))
        accent2_btn = QPushButton("Color secundario…")
        accent2_btn.clicked.connect(lambda: self._pick_color("app.accent2"))
        reset_btn = QPushButton("Restablecer colores del tema")
        reset_btn.clicked.connect(self._reset_colors)
        lay.addWidget(self._section("Apariencia", [
            ("Tema", self.theme), (None, self.compact), (None, accent_btn), (None, accent2_btn), (None, reset_btn)]))

        # ---- Sistema
        self.autostart = QCheckBox("Iniciar Gamesword con Windows")
        self.autostart.setChecked(autostart.is_enabled())
        self.start_min = QCheckBox("Iniciar minimizado en la bandeja")
        self.start_min.setChecked(bool(s.get("app.start_minimized")))
        self.tray = QCheckBox("Al cerrar la ventana, seguir en la bandeja del sistema")
        self.tray.setChecked(bool(s.get("app.close_to_tray")))
        self.hotkeys = QCheckBox(f"Atajos globales: {HOTKEY_LABELS['toggle']} mostrar/ocultar · "
                                 f"{HOTKEY_LABELS['voice']} hablar con la IA")
        self.hotkeys.setChecked(bool(s.get("app.hotkeys", True)))
        self.gamepad = QCheckBox("Navegar con mando (Xbox/XInput) cuando Gamesword tenga el foco")
        self.gamepad.setChecked(bool(s.get("app.gamepad", True)))
        self.minimize = QCheckBox("Minimizar Gamesword al iniciar un juego")
        self.minimize.setChecked(bool(s.get("app.minimize_on_game_launch")))
        self.discord = QLineEdit(s.get("discord.app_id", ""))
        self.discord.setPlaceholderText("Application ID de Discord (opcional)")
        lay.addWidget(self._section("Sistema", [
            (None, self.autostart), (None, self.start_min), (None, self.tray), (None, self.hotkeys),
            (None, self.gamepad), (None, self.minimize), ("Discord Rich Presence", self.discord),
            (None, muted("Para mostrar «Jugando a…» en Discord: crea una aplicación en discord.com/developers, copia "
                         "su Application ID aquí e instala pypresence (pip install pypresence).", wrap=True))]))

        # ---- Biblioteca
        self.auto_scan = QCheckBox("Buscar juegos nuevos al iniciar Gamesword")
        self.auto_scan.setChecked(bool(s.get("app.auto_scan_on_start")))
        self.covers = QCheckBox("Descargar portadas automáticamente")
        self.covers.setChecked(bool(s.get("app.fetch_covers")))
        self.rawg = QLineEdit(s.get("covers.rawg_key", ""))
        self.rawg.setEchoMode(QLineEdit.EchoMode.Password)
        self.rawg.setPlaceholderText("Clave gratuita de rawg.io/apidocs (portadas de juegos que no son de Steam)")
        self.sync_owned = QCheckBox("Incluir en la biblioteca los juegos de mi cuenta que no tengo instalados")
        self.sync_owned.setChecked(bool(s.get("app.sync_owned", True)))
        self.steam_id = QLineEdit(s.get("steam.steam_id", ""))
        self.steam_id.setPlaceholderText("SteamID64 (opcional: se detecta solo desde Steam)")
        self.steam_key = QLineEdit(s.get("steam.api_key", ""))
        self.steam_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.steam_key.setPlaceholderText("Clave de la API de Steam (steamcommunity.com/dev/apikey)")
        self.steam_all = QCheckBox("Añadir también los juegos que tengo en Steam pero no instalados")
        steam_btn = QPushButton("Importar mis horas de Steam")
        steam_btn.clicked.connect(self._steam_import)
        self.steam_msg = muted("", wrap=True)
        unhide = QPushButton("Restaurar juegos ocultos")
        unhide.clicked.connect(self._unhide)
        lay.addWidget(self._section("Biblioteca", [
            (None, self.auto_scan), (None, self.sync_owned), (None, self.covers), ("Clave RAWG", self.rawg),
            (None, unhide),
            ("SteamID64", self.steam_id), ("Clave API Steam", self.steam_key), (None, self.steam_all),
            (None, steam_btn), (None, self.steam_msg),
            (None, muted("Steam: con tu clave de API aparecen TODOS tus juegos (también los no instalados) y se "
                         "importan tus horas; tu perfil y los «detalles de juego» deben estar en Público. "
                         "Epic: instala «legendary» (pip install legendary-gl) y ejecuta «legendary auth» una vez. "
                         "Ubisoft, EA, Xbox, Battle.net y GOG: se leen de GOG Galaxy 2.0 si lo usas con esas cuentas "
                         "conectadas. Ninguna plataforma da acceso directo a tu catálogo sin esto.", wrap=True))]))

        # ---- IA
        self.provider = QComboBox()
        for key, name, *_ in PROVIDERS:
            self.provider.addItem(name, key)
        self.provider.setCurrentIndex(max(0, self.provider.findData(s.get("ai.provider"))))
        self.provider.currentIndexChanged.connect(self._provider_changed)
        self.base_url = QLineEdit(s.get("ai.base_url", ""))
        self.model = QLineEdit(s.get("ai.model", ""))
        self.api_key = QLineEdit(s.get("ai.api_key", ""))
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key.setPlaceholderText("sk-…  (también se lee la variable de entorno OPENAI_API_KEY)")
        self.use_tools = QCheckBox("Usar herramientas nativas del modelo (abrir juegos, horas, recomendaciones)")
        self.use_tools.setChecked(bool(s.get("ai.use_tools", True)))
        self.stream = QCheckBox("Mostrar la respuesta mientras se escribe")
        self.stream.setChecked(bool(s.get("ai.stream", True)))
        test = QPushButton("Probar conexión")
        test.clicked.connect(self._test_ai)
        self.ai_msg = muted("", wrap=True)
        self.memory_on = QCheckBox("Memoria: que Gamesword AI recuerde lo que le pida («recuerda que…»)")
        self.memory_on.setChecked(bool(s.get("ai.memory_enabled", True)))
        mem_btn = QPushButton("Ver o borrar la memoria…")
        mem_btn.clicked.connect(lambda: MemoryDialog(self, self.ctx.db).exec())
        cmd_btn = QPushButton("Comandos personalizados…")
        cmd_btn.clicked.connect(lambda: CustomCommandsDialog(self, self.ctx.settings).exec())
        storage = ("Las claves se guardan en el Administrador de credenciales de Windows." if s.secrets_secure else
                   "Sin la librería «keyring» las claves se guardan en data/settings.json en texto plano. "
                   "Instala keyring (pip install keyring) para guardarlas cifradas.")
        lay.addWidget(self._section("Inteligencia artificial", [
            ("Proveedor", self.provider), ("Dirección API", self.base_url), ("Modelo", self.model),
            ("Clave API", self.api_key), (None, self.use_tools), (None, self.stream), (None, self.memory_on),
            (None, mem_btn), (None, cmd_btn), (None, test),
            (None, self.ai_msg), (None, muted(storage + " Los modelos cambian con el tiempo: si uno deja de "
                                              "existir, escribe otro.", wrap=True))]))

        # ---- Voz
        self.speak = QCheckBox("Leer en voz alta las respuestas de Gamesword AI")
        self.speak.setChecked(bool(s.get("voice.speak_responses")))
        self.lang = QComboBox()
        for code, name in LANGS:
            self.lang.addItem(name, code)
        self.lang.setCurrentIndex(max(0, self.lang.findData(s.get("voice.language"))))
        self.stt = QComboBox()
        self.stt.addItem("Google (en la nube, más ligero)", "google")
        self.stt.addItem("Local con Whisper (privado, sin enviar audio)", "local")
        self.stt.setCurrentIndex(max(0, self.stt.findData(s.get("voice.stt_engine"))))
        self.whisper = QComboBox()
        for m in ("tiny", "base", "small"):
            self.whisper.addItem(m, m)
        self.whisper.setCurrentIndex(max(0, self.whisper.findData(s.get("voice.whisper_model"))))
        self.wake = QCheckBox("Palabra de activación: decir «Oye Gamesword» (solo con Whisper local)")
        self.wake.setChecked(bool(s.get("voice.wake_word")))
        self.rate = self._slider(100, 280, int(s.get("voice.rate", 185)))
        self.volume = self._slider(0, 100, int(float(s.get("voice.volume", 0.9)) * 100))
        voice_test = QPushButton("Probar voz")
        voice_test.clicked.connect(self._test_voice)
        lay.addWidget(self._section("Voz", [
            (None, self.speak), ("Idioma", self.lang), ("Reconocimiento", self.stt), ("Modelo Whisper", self.whisper),
            (None, self.wake), ("Velocidad", self.rate), ("Volumen", self.volume), (None, voice_test),
            (None, muted("Con «Google» el audio del micrófono se envía a ese servicio. El modo local necesita "
                         "pip install faster-whisper (descarga el modelo la primera vez) y usa el procesador.",
                         wrap=True))]))

        # ---- Online
        self.enabled = QCheckBox("Activar funciones online (amigos, grupos e invitaciones)")
        self.enabled.setChecked(bool(s.get("social.enabled")))
        self.server = QLineEdit(s.get("social.server_url", ""))
        self.share = QCheckBox("Mostrar a mis amigos a qué estoy jugando")
        self.share.setChecked(bool(s.get("social.share_activity", True)))
        self.verify_tls = QCheckBox("Verificar el certificado HTTPS (desactívalo solo con tu propio certificado "
                                    "autofirmado)")
        self.verify_tls.setChecked(bool(s.get("social.verify_tls", True)))
        lay.addWidget(self._section("Online", [(None, self.enabled), ("Servidor", self.server), (None, self.share),
                                               (None, self.verify_tls)]))

        # ---- Actualizaciones
        self.update_url = QLineEdit(s.get("app.update_url", ""))
        self.update_url.setPlaceholderText("https://tudominio.com/update.json")
        self.check_start = QCheckBox("Buscar actualizaciones al iniciar")
        self.check_start.setChecked(bool(s.get("app.check_updates", True)))
        upd_btn = QPushButton("Buscar actualizaciones ahora")
        upd_btn.clicked.connect(self._check_now)
        self.telemetry = QCheckBox("Enviar estadísticas anónimas de uso (desactivado por defecto)")
        self.telemetry.setChecked(bool(s.get("app.telemetry")))
        lay.addWidget(self._section("Actualizaciones y privacidad", [
            ("Manifiesto", self.update_url), (None, self.check_start), (None, upd_btn), (None, self.telemetry),
            (None, muted("La telemetría solo envía un ID aleatorio, la versión y «start» al servidor de arriba. "
                         "Nada de juegos, rutas ni chats.", wrap=True))]))

        # ---- Licencia
        self.license = QPlainTextEdit(s.get("license.key", ""))
        self.license.setPlaceholderText("Pega aquí tu licencia Plus o Pro")
        self.license.setFixedHeight(70)
        act = QPushButton("Activar licencia")
        act.clicked.connect(self._activate_license)
        self.license_msg = muted(self._license_text(), wrap=True)
        lay.addWidget(self._section("Licencia", [(None, self.license), (None, act), (None, self.license_msg)]))

        # ---- Copias de seguridad
        self.auto_backup = QCheckBox("Crear una copia automática cada día al abrir Gamesword (se guardan las 7 últimas)")
        self.auto_backup.setChecked(bool(s.get("app.auto_backup", True)))
        b_now = primary(QPushButton("Crear copia ahora"))
        b_now.clicked.connect(self._backup_now)
        b_restore = QPushButton("Restaurar una copia…")
        b_restore.clicked.connect(self._restore)
        b_folder = QPushButton("Abrir carpeta de copias")
        b_folder.clicked.connect(lambda: open_in_explorer(backup.backups_dir() / "x"))
        self.backup_msg = muted(self._backup_text(), wrap=True)
        lay.addWidget(self._section("Copias de seguridad", [
            (None, self.auto_backup), (None, b_now), (None, b_restore), (None, b_folder), (None, self.backup_msg),
            (None, muted("La copia incluye tu biblioteca, horas, colecciones, logros y ajustes, pero NUNCA tus claves. "
                         "Si la base de datos se daña, Gamesword restaura la última copia buena al abrir.",
                         wrap=True))]))

        # ---- Datos y soporte
        folder = QPushButton("Abrir carpeta de datos")
        folder.clicked.connect(lambda: open_in_explorer(data_dir()))
        report = QPushButton("Crear informe de diagnóstico")
        report.clicked.connect(self._report)
        clear = QPushButton("Borrar historial del chat con la IA")
        clear.clicked.connect(lambda: (self.ctx.db.clear_chat(), self.notify("Historial borrado.")))
        lay.addWidget(self._section("Datos y soporte", [
            (None, folder), (None, report), (None, clear),
            (None, muted("El informe es un .zip con logs, versiones y ajustes SIN claves. Adjúntalo si pides ayuda.",
                         wrap=True))]))

        save = primary(QPushButton("Guardar cambios"))
        save.setMinimumHeight(40)
        save.clicked.connect(self._save)
        self.saved = muted("", wrap=False)
        row = QHBoxLayout()
        row.addWidget(save)
        row.addWidget(self.saved)
        row.addStretch()
        lay.addLayout(row)
        lay.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(inner)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll)

    # ----------------------------------------------------------- utilidades
    @staticmethod
    def _slider(lo: int, hi: int, value: int) -> QSlider:
        sl = QSlider(Qt.Orientation.Horizontal)
        sl.setRange(lo, hi)
        sl.setValue(value)
        return sl

    @staticmethod
    def _section(title: str, rows) -> QWidget:
        box = card_frame()
        v = QVBoxLayout(box)
        v.setContentsMargins(22, 18, 22, 18)
        v.setSpacing(10)
        v.addWidget(h2(title))
        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        for lab, w in rows:
            if lab:
                form.addRow(lab, w)
            else:
                form.addRow(w)
        v.addLayout(form)
        return box

    def refresh(self) -> None:
        self.license_msg.setText(self._license_text())
        self.backup_msg.setText(self._backup_text())

    def _backup_text(self) -> str:
        last = self.ctx.settings.get("app.last_backup", "")
        n = len(backup.list_backups())
        return (f"Última copia: {last.replace('T', ' ')}  ·  {n} guardadas." if last else "Todavía no hay copias.")

    def _license_text(self) -> str:
        info = self.ctx.license.info()
        extra = "" if licensing.ENFORCE_LICENSES else " Ahora mismo todas las funciones están desbloqueadas."
        if info.valid:
            return f"✔ {info.message} Titular: {info.name or '—'}.{extra}"
        return info.message + extra

    # -------------------------------------------------------------- acciones
    def _apply_theme(self) -> None:
        key = self.theme.currentData()
        self.ctx.settings.set("app.theme", key)
        self._record("customizations")
        if callable(self.theme_changed):
            self.theme_changed(key)

    def _record(self, counter: str) -> None:
        try:
            self.ctx.progress.record(counter)
        except Exception:  # noqa: BLE001
            pass

    def _appearance_changed(self) -> None:
        self.ctx.settings.set("app.compact", self.compact.isChecked())
        self._record("customizations")
        if callable(self.theme_changed):
            self.theme_changed(self.theme.currentData())

    def _pick_color(self, key: str) -> None:
        start = QColor(self.ctx.settings.get(key) or theme.current().get("accent" if key == "app.accent" else "accent2"))
        color = QColorDialog.getColor(start, self, "Elegir color")
        if color.isValid():
            self.ctx.settings.set(key, color.name())
            self._record("customizations")
            if callable(self.theme_changed):
                self.theme_changed(self.theme.currentData())

    def _reset_colors(self) -> None:
        self.ctx.settings.set("app.accent", "", save=False)
        self.ctx.settings.set("app.accent2", "")
        if callable(self.theme_changed):
            self.theme_changed(self.theme.currentData())

    def _backup_now(self) -> None:
        try:
            path = backup.create_backup(self.ctx.db.path, self.ctx.settings, VERSION)
        except backup.BackupError as exc:
            self.notify(str(exc))
            return
        self._record("backups")
        self.backup_msg.setText(self._backup_text())
        self.notify(f"Copia creada: {path.name}")

    def _restore(self) -> None:
        start = backup.list_backups()[0] if backup.list_backups() else backup.backups_dir()
        path, _ = QFileDialog.getOpenFileName(self, "Elegir copia de seguridad", str(start), "Copias (*.zip)")
        if not path:
            return
        if QMessageBox.question(self, "Restaurar copia",
                                "Se reemplazarán tu biblioteca, horas, colecciones y logros actuales por los de la "
                                "copia. Antes se guarda una copia de seguridad de lo actual.\n\n¿Continuar?") \
                != QMessageBox.StandardButton.Yes:
            return
        try:
            backup.restore_backup(Path(path), self.ctx.db.path, self.ctx.settings)
        except backup.BackupError as exc:
            QMessageBox.warning(self, "Restaurar copia", str(exc))
            return
        self.notify("Copia restaurada. Reinicia Gamesword para ver todos los ajustes.")
        if callable(self.on_restored):
            self.on_restored()

    def _provider_changed(self) -> None:
        key = self.provider.currentData()
        for k, _, url, model in PROVIDERS:
            if k == key and url:
                self.base_url.setText(url)
                self.model.setText(model)

    def _unhide(self) -> None:
        n = self.ctx.db.unhide_all()
        self.notify(f"{n} juegos restaurados." if n else "No había juegos ocultos.")

    def _collect_ai(self) -> None:
        s = self.ctx.settings
        s.set("ai.provider", self.provider.currentData(), save=False)
        s.set("ai.base_url", self.base_url.text().strip(), save=False)
        s.set("ai.model", self.model.text().strip(), save=False)
        s.set("ai.api_key", self.api_key.text().strip(), save=False)

    def _test_ai(self) -> None:
        self._collect_ai()
        self.ai_msg.setText("Probando…")
        run_async(self.ctx.assistant.test_connection, lambda m: self.ai_msg.setText(m),
                  lambda e: self.ai_msg.setText(f"Error: {e}"))

    def _test_voice(self) -> None:
        v = self.ctx.voice
        self.ctx.settings.set("voice.rate", self.rate.value(), save=False)
        self.ctx.settings.set("voice.volume", self.volume.value() / 100, save=False)
        self.ctx.settings.set("voice.language", self.lang.currentData(), save=False)
        if not v.tts_available:
            QMessageBox.information(self, "Voz no disponible", v.missing_hint("tts"))
            return
        v.speak("Hola, soy Gamesword AI. ¿A qué jugamos hoy?")

    def _steam_import(self) -> None:
        s = self.ctx.settings
        s.set("steam.steam_id", self.steam_id.text().strip(), save=False)
        s.set("steam.api_key", self.steam_key.text().strip())
        self.steam_msg.setText("Importando…")

        def work():
            from core.game_detector import steam_user_id
            return import_playtime(self.ctx.db, s.get("steam.api_key"),
                                   s.get("steam.steam_id") or steam_user_id() or "", self.steam_all.isChecked())

        def done(r):
            self.steam_msg.setText(f"✔ {r.updated} juegos actualizados"
                                   + (f", {r.added} añadidos" if r.added else "") + f" (tienes {r.total_owned} en Steam).")

        run_async(work, done, lambda e: self.steam_msg.setText(str(e) if isinstance(e, SteamImportError)
                                                              else f"Error: {e}"))

    def _check_now(self) -> None:
        self.ctx.settings.set("app.update_url", self.update_url.text().strip())
        if callable(self.check_updates):
            self.check_updates(True)

    def _activate_license(self) -> None:
        info = self.ctx.license.activate(self.license.toPlainText())
        self.license_msg.setText(self._license_text() if info.valid else info.message)

    def _report(self) -> None:
        path = diagnostics.create_report(self.ctx.settings, self.ctx)
        self.notify(f"Informe creado: {path.name}")
        open_in_explorer(path)

    def _save(self) -> None:
        s = self.ctx.settings
        self._collect_ai()
        for key, widget in (("app.auto_scan_on_start", self.auto_scan), ("app.sync_owned", self.sync_owned), ("app.fetch_covers", self.covers),
                            ("app.minimize_on_game_launch", self.minimize), ("app.start_minimized", self.start_min),
                            ("app.close_to_tray", self.tray), ("app.hotkeys", self.hotkeys),
                            ("app.gamepad", self.gamepad), ("app.check_updates", self.check_start),
                            ("app.telemetry", self.telemetry), ("ai.use_tools", self.use_tools), ("ai.memory_enabled", self.memory_on), ("app.auto_backup", self.auto_backup),
                            ("ai.stream", self.stream), ("voice.speak_responses", self.speak),
                            ("voice.wake_word", self.wake), ("social.enabled", self.enabled),
                            ("social.share_activity", self.share), ("social.verify_tls", self.verify_tls)):
            s.set(key, widget.isChecked(), save=False)
        s.set("covers.rawg_key", self.rawg.text().strip(), save=False)
        s.set("steam.steam_id", self.steam_id.text().strip(), save=False)
        s.set("steam.api_key", self.steam_key.text().strip(), save=False)
        s.set("discord.app_id", self.discord.text().strip(), save=False)
        s.set("voice.language", self.lang.currentData(), save=False)
        s.set("voice.stt_engine", self.stt.currentData(), save=False)
        s.set("voice.whisper_model", self.whisper.currentData(), save=False)
        s.set("voice.rate", self.rate.value(), save=False)
        s.set("voice.volume", self.volume.value() / 100, save=False)
        s.set("social.server_url", self.server.text().strip(), save=False)
        s.set("app.update_url", self.update_url.text().strip(), save=False)
        s.save()
        if not autostart.set_enabled(self.autostart.isChecked()) and self.autostart.isChecked():
            self.notify("No se pudo activar el inicio con Windows (solo disponible en Windows).")
        if callable(self.on_saved):
            self.on_saved()
        self.saved.setText("✔ Guardado")
        self.notify("Ajustes guardados.")
