"""Gamesword AI: chat inteligente con voz."""
import html
import re

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (QCheckBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea,
                               QSizePolicy, QVBoxLayout, QWidget)

from ai.voice import VoiceError
from utils.qt_async import call_in_main, run_async
from .widgets import BaseView, h1, muted, primary

WELCOME = ("¡Hola! Soy **Gamesword AI** 🎮\n"
           "Puedo abrir tus juegos («Ábreme Fortnite», «Abre Discord y después Rocket League»), contarte tus horas "
           "(«¿Cuántas horas he jugado esta semana?»), recomendarte juegos («algo parecido a GTA V») y, con una clave "
           "de IA en Ajustes, ayudarte con configuración, rendimiento y trucos. Escribe o pulsa 🎙 para hablar.")

SUGGESTIONS = ["¿Qué juegos tengo instalados?", "¿Cuántas horas he jugado esta semana?",
               "Quiero jugar a algo parecido a GTA V", "Busca juegos cooperativos para jugar con amigos"]


def to_html(text: str) -> str:
    safe = html.escape(text)
    safe = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", safe)
    return safe.replace("\n", "<br>")


class Bubble(QFrame):
    def __init__(self, text: str, user: bool):
        super().__init__()
        self.setObjectName("BubbleUser" if user else "BubbleAI")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 11, 16, 11)
        self.lbl = QLabel(to_html(text))
        self.lbl.setTextFormat(Qt.TextFormat.RichText)
        self.lbl.setWordWrap(True)
        self.lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.lbl.setMaximumWidth(620)
        lay.addWidget(self.lbl)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)

    def set_text(self, text: str) -> None:
        self.lbl.setText(to_html(text))


class AIChatView(BaseView):
    def __init__(self, ctx):
        super().__init__(ctx)
        self._busy = False
        self._typing = None
        self._loaded = False
        self._speak_once = False

        head = QHBoxLayout()
        head.addWidget(h1("Gamesword AI"))
        self.state = muted("", wrap=False)
        head.addWidget(self.state)
        head.addStretch()
        self.speak = QCheckBox("🔊 Leer respuestas")
        self.speak.setChecked(bool(ctx.settings.get("voice.speak_responses")))
        self.speak.toggled.connect(self._speak_toggled)
        clear = QPushButton("🗑 Borrar chat")
        clear.clicked.connect(self._clear)
        head.addWidget(self.speak)
        head.addWidget(clear)

        self.msgs = QVBoxLayout()
        self.msgs.setSpacing(10)
        self.msgs.setContentsMargins(4, 4, 4, 4)
        self.msgs.addStretch()
        holder = QWidget()
        holder.setLayout(self.msgs)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setWidget(holder)

        self.chips = QHBoxLayout()
        self.chips.setSpacing(8)
        for s in SUGGESTIONS:
            b = QPushButton(s)
            b.setProperty("chip", True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, t=s: self.send(t))
            self.chips.addWidget(b)
        self.chips.addStretch()

        self.input = QLineEdit()
        self.input.setPlaceholderText("Escribe un mensaje o un comando…  (Enter para enviar)")
        self.input.returnPressed.connect(lambda: self.send())
        self.mic = QPushButton("🎙")
        self.mic.setFixedWidth(52)
        self.mic.setToolTip("Hablar con Gamesword AI")
        self.mic.clicked.connect(self._listen)
        self.send_btn = primary(QPushButton("Enviar"))
        self.send_btn.setMinimumWidth(96)
        self.send_btn.clicked.connect(lambda: self.send())
        bar = QHBoxLayout()
        bar.setSpacing(8)
        bar.addWidget(self.input, 1)
        bar.addWidget(self.mic)
        bar.addWidget(self.send_btn)

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 20)
        root.setSpacing(12)
        root.addLayout(head)
        root.addWidget(self.scroll, 1)
        root.addLayout(self.chips)
        root.addLayout(bar)

    # ------------------------------------------------------------- historial
    def refresh(self) -> None:
        if not self._loaded:
            self._loaded = True
            history = self.ctx.db.get_chat(20)
            if not history:
                self._add(WELCOME, False)
            for m in history:
                self._add(m["content"], m["role"] == "user")
        a = self.ctx.assistant
        self.state.setText("· conectado a un modelo de IA" if a and a.has_llm
                           else "· modo local (sin clave de IA: comandos y recomendaciones)")
        self.input.setFocus()

    def _add(self, text: str, user: bool) -> Bubble:
        b = Bubble(text, user)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        if user:
            row.addStretch()
            row.addWidget(b)
        else:
            row.addWidget(b)
            row.addStretch()
        container = QWidget()
        container.setLayout(row)
        self.msgs.insertWidget(self.msgs.count() - 1, container)
        QTimer.singleShot(60, lambda: self.scroll.verticalScrollBar().setValue(
            self.scroll.verticalScrollBar().maximum()))
        return b

    def _add_confirm(self, pending) -> None:
        """Pregunta de confirmación con botones: la acción importante solo se ejecuta si se pulsa «Sí»."""
        box = QFrame()
        box.setObjectName("Card")
        lay = QHBoxLayout(box)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(10)
        q = QLabel(pending.prompt)
        q.setWordWrap(True)
        yes = primary(QPushButton("Sí, hazlo"))
        no = QPushButton("Cancelar")
        lay.addWidget(q, 1)
        lay.addWidget(yes)
        lay.addWidget(no)
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(box)
        row.addStretch()
        self.msgs.insertWidget(self.msgs.count() - 1, container)
        QTimer.singleShot(60, self._scroll_down)

        def decide(ok: bool) -> None:
            yes.setEnabled(False)
            no.setEnabled(False)
            run_async(self.ctx.assistant.execute_pending,
                      lambda r: (container.deleteLater(), self._add(r.text, False), self._after_action(r)),
                      lambda e: (container.deleteLater(), self._add(f"No se pudo completar: {e}", False)), ok)
        yes.clicked.connect(lambda: decide(True))
        no.clicked.connect(lambda: decide(False))

    def _after_action(self, reply) -> None:
        if self.speak.isChecked():
            self.ctx.voice.speak(reply.text)

    def _scroll_down(self) -> None:
        bar = self.scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    def listen_now(self) -> None:
        """Usado por el atajo global Ctrl+Alt+V."""
        self._listen()

    def _clear(self) -> None:
        self.ctx.db.clear_chat()
        while self.msgs.count() > 1:
            item = self.msgs.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._add(WELCOME, False)

    def _speak_toggled(self, on: bool) -> None:
        self.ctx.settings.set("voice.speak_responses", on)
        if on and not self.ctx.voice.tts_available:
            self.notify(self.ctx.voice.missing_hint("tts"))

    # ---------------------------------------------------------------- enviar
    def send(self, text: str = None, speak: bool = False) -> None:
        text = (text if isinstance(text, str) else self.input.text()).strip()
        if not text or self._busy:
            return
        self.input.clear()
        self._speak_once = speak
        self._add(text, True)
        self._set_busy(True)
        self._typing = self._add("Gamesword AI está pensando…", False)
        bubble = self._typing

        def on_token(partial: str) -> None:           # llega desde el hilo del modelo: pasar al hilo de la interfaz
            call_in_main(lambda: bubble.set_text(partial))
            call_in_main(self._scroll_down)
        run_async(self.ctx.assistant.respond, self._answer, self._failed, text, on_token=on_token)

    def _answer(self, reply) -> None:
        if self._typing:
            self._typing.set_text(reply.text)
            self._typing = None
        self._set_busy(False)
        if self.speak.isChecked() or self._speak_once:
            self._speak_once = False
            self.ctx.voice.speak(reply.text)
        if reply.launched:
            self.notify("Abierto: " + ", ".join(reply.launched))
        if reply.pending:
            self._add_confirm(reply.pending)

    def _failed(self, exc) -> None:
        if self._typing:
            self._typing.set_text(f"Ups, algo ha fallado: {exc}")
            self._typing = None
        self._set_busy(False)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.send_btn.setEnabled(not busy)
        self.input.setEnabled(not busy)
        if not busy:
            self.input.setFocus()

    # ------------------------------------------------------------------ voz
    def _listen(self) -> None:
        if self._busy:
            return
        if not self.ctx.voice.stt_available:
            self.notify(self.ctx.voice.missing_hint("stt"))
            self._add("🎙 " + self.ctx.voice.missing_hint("stt"), False)
            return
        self.mic.setEnabled(False)
        self.mic.setText("…")
        self.state.setText("· escuchando, habla ahora")

        def done(text):
            self._mic_reset()
            self.send(text)

        def failed(exc):
            self._mic_reset()
            self.notify(str(exc) if isinstance(exc, VoiceError) else f"Error de micrófono: {exc}")

        run_async(self.ctx.voice.listen, done, failed)

    def _mic_reset(self) -> None:
        self.mic.setEnabled(True)
        self.mic.setText("🎙")
        self.refresh()
