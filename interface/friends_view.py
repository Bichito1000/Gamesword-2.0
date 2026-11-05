"""Amigos: cuenta, estado, lista, invitaciones a jugar, grupos con chat (requiere el servidor de Gamesword)."""
import html

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QInputDialog, QLineEdit, QListWidget, QListWidgetItem,
                               QMessageBox, QPushButton, QTextBrowser, QVBoxLayout, QWidget)

from utils.qt_async import run_async
from . import theme
from .widgets import BaseView, card_frame, h1, h2, label, muted, primary

STATUS = [("online", "En línea"), ("away", "Ausente"), ("dnd", "No molestar")]
STATUS_COLOR = {"online": "#34d399", "away": "#fbbf24", "dnd": "#f43f5e", "offline": "#6b6b90"}
STATUS_LABEL = {"online": "En línea", "away": "Ausente", "dnd": "No molestar", "offline": "Desconectado"}


class FriendsView(BaseView):
    def __init__(self, ctx):
        super().__init__(ctx)
        self._friends, self._groups = [], []
        self._chat_group = None
        self._last_msg = 0
        self._chat_busy = False

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 20)
        root.setSpacing(14)
        head = QHBoxLayout()
        head.addWidget(h1("Amigos"))
        head.addStretch()
        self.logout_btn = QPushButton("Cerrar sesión")
        self.logout_btn.clicked.connect(self._logout)
        self.reload = QPushButton("⟳  Actualizar")
        self.reload.clicked.connect(self.refresh)
        head.addWidget(self.logout_btn)
        head.addWidget(self.reload)
        root.addLayout(head)

        # ---- panel de acceso (sin sesión)
        self.connect_card = card_frame()
        cl = QVBoxLayout(self.connect_card)
        cl.setContentsMargins(22, 18, 22, 18)
        cl.setSpacing(10)
        cl.addWidget(h2("Conéctate con tus amigos"))
        cl.addWidget(muted("Las funciones sociales usan un servidor de Gamesword (carpeta «server»). Para probar en "
                           "tu PC ejecuta INICIAR_SERVIDOR.bat; para jugar con amigos, alójalo en un equipo "
                           "accesible para todos y pon aquí su dirección (mejor con https://).", wrap=True))
        self.server = QLineEdit(ctx.settings.get("social.server_url", ""))
        self.server.setPlaceholderText("http://127.0.0.1:8000")
        self.username = QLineEdit(ctx.settings.get("social.username", "") or ctx.settings.get("profile.username", ""))
        self.username.setPlaceholderText("Nombre de usuario (3-20 caracteres)")
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setPlaceholderText("Contraseña (mínimo 8 caracteres)")
        self.password.returnPressed.connect(self._login)
        row = QHBoxLayout()
        self.login_btn = primary(QPushButton("Iniciar sesión"))
        self.login_btn.clicked.connect(self._login)
        self.join_btn = QPushButton("Crear cuenta")
        self.join_btn.clicked.connect(self._register)
        row.addWidget(self.login_btn)
        row.addWidget(self.join_btn)
        self.conn_msg = muted("", wrap=True)
        for w in (self.server, self.username, self.password):
            cl.addWidget(w)
        cl.addLayout(row)
        cl.addWidget(self.conn_msg)
        root.addWidget(self.connect_card)

        # ---- panel principal (con sesión)
        self.main = QWidget()
        ml = QHBoxLayout(self.main)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(16)

        left = card_frame()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(20, 18, 20, 18)
        ll.setSpacing(8)
        self.me_name = label("", "H2")
        self.me_code = label("", "Muted")
        self.insecure = label("", "Danger")
        self.insecure.setWordWrap(True)
        copy = QPushButton("Copiar código de amigo")
        copy.clicked.connect(self._copy_code)
        self.status = QComboBox()
        for k, lab in STATUS:
            self.status.addItem(lab, k)
        self.status.currentIndexChanged.connect(self._status_changed)
        for w in (self.me_name, self.me_code, copy, self.insecure):
            ll.addWidget(w)
        ll.addSpacing(6)
        ll.addWidget(muted("Tu estado", wrap=False))
        ll.addWidget(self.status)
        ll.addSpacing(10)
        ll.addWidget(muted("Añadir amigo por código", wrap=False))
        self.code_in = QLineEdit()
        self.code_in.setPlaceholderText("Ej.: K7P2QD")
        self.code_in.setMaxLength(8)
        add = primary(QPushButton("Añadir"))
        add.clicked.connect(self._add_friend)
        self.code_in.returnPressed.connect(self._add_friend)
        ll.addWidget(self.code_in)
        ll.addWidget(add)
        ll.addStretch()
        left.setFixedWidth(270)

        mid = QVBoxLayout()
        mid.addWidget(h2("Lista de amigos"))
        self.flist = QListWidget()
        self.flist.setObjectName("List")
        mid.addWidget(self.flist, 1)
        frow = QHBoxLayout()
        inv = primary(QPushButton("🎮 Invitar a jugar"))
        inv.clicked.connect(self._invite)
        rm = QPushButton("Eliminar")
        rm.setProperty("danger", True)
        rm.clicked.connect(self._remove_friend)
        frow.addWidget(inv)
        frow.addWidget(rm)
        mid.addLayout(frow)

        right = QVBoxLayout()
        right.addWidget(h2("Grupos"))
        self.glist = QListWidget()
        self.glist.setObjectName("List")
        self.glist.setMaximumHeight(170)
        self.glist.currentItemChanged.connect(self._group_selected)
        right.addWidget(self.glist)
        grow = QHBoxLayout()
        new = primary(QPushButton("Crear"))
        new.clicked.connect(self._create_group)
        join = QPushButton("Unirme")
        join.clicked.connect(self._join_group)
        leave = QPushButton("Salir")
        leave.setProperty("danger", True)
        leave.clicked.connect(self._leave_group)
        for b in (new, join, leave):
            grow.addWidget(b)
        right.addLayout(grow)
        self.chat_title = h2("Chat del grupo")
        right.addWidget(self.chat_title)
        self.chat = QTextBrowser()
        self.chat.setOpenLinks(False)
        right.addWidget(self.chat, 1)
        crow = QHBoxLayout()
        self.chat_in = QLineEdit()
        self.chat_in.setPlaceholderText("Escribe un mensaje…")
        self.chat_in.setMaxLength(500)
        self.chat_in.returnPressed.connect(self._send_chat)
        send = primary(QPushButton("Enviar"))
        send.clicked.connect(self._send_chat)
        crow.addWidget(self.chat_in, 1)
        crow.addWidget(send)
        right.addLayout(crow)

        ml.addWidget(left)
        ml.addLayout(mid, 1)
        ml.addLayout(right, 1)
        root.addWidget(self.main, 1)

        self.timer = QTimer(self)
        self.timer.setInterval(20000)
        self.timer.timeout.connect(self._load)
        self.chat_timer = QTimer(self)
        self.chat_timer.setInterval(4000)
        self.chat_timer.timeout.connect(self._poll_chat)

    # ---------------------------------------------------------------- vida
    def showEvent(self, e):
        super().showEvent(e)
        self.timer.start()
        self.chat_timer.start()

    def hideEvent(self, e):
        super().hideEvent(e)
        self.timer.stop()
        self.chat_timer.stop()

    def refresh(self) -> None:
        s = self.ctx.social
        self.connect_card.setVisible(not s.registered)
        self.main.setVisible(s.registered)
        self.logout_btn.setVisible(s.registered)
        if not s.registered:
            return
        st = self.ctx.settings
        self.me_name.setText(st.get("social.username", ""))
        self.me_code.setText(f"Código de amigo: {st.get('social.friend_code', '—')}")
        self.insecure.setText("⚠ Conexión sin cifrar (http). Tu contraseña viaja sin protección; usa https:// "
                              "si el servidor no está en tu red." if s.insecure else "")
        self.status.blockSignals(True)
        self.status.setCurrentIndex(max(0, self.status.findData(st.get("social.status", "online"))))
        self.status.blockSignals(False)
        self._load()

    def _load(self) -> None:
        if not self.ctx.social.registered:
            return

        def fetch():          # el «latido» y las invitaciones los gestiona la ventana principal
            return self.ctx.social.friends(), self.ctx.social.groups()
        run_async(fetch, self._loaded, self._load_failed)

    def _load_failed(self, exc) -> None:
        self.notify(f"Amigos: {exc}")
        self.refresh() if not self.ctx.social.registered else None

    def _loaded(self, data) -> None:
        self._friends, self._groups = data
        cur_f = self._current_id(self.flist)
        self.flist.clear()
        if not self._friends:
            self.flist.addItem("Aún no tienes amigos. Comparte tu código o añade el de otra persona.")
        for f in self._friends:
            st = f.get("status", "offline")
            text = f"●  {f['username']}   —   {STATUS_LABEL.get(st, st)}"
            if f.get("playing") and st != "offline":
                text += f"  ·  🎮 {f['playing']}"
            it = QListWidgetItem(text)
            it.setData(Qt.ItemDataRole.UserRole, f["user_id"])
            it.setForeground(QColor(STATUS_COLOR.get(st, "#aaaaaa")) if st != "online" else QColor("#e8e8ff"))
            self.flist.addItem(it)
            if f["user_id"] == cur_f:
                self.flist.setCurrentItem(it)
        cur_g = self._chat_group
        self.glist.blockSignals(True)
        self.glist.clear()
        if not self._groups:
            self.glist.addItem("Sin grupos. Crea uno para quedar a jugar.")
        for g in self._groups:
            members = ", ".join(m["username"] for m in g["members"])
            it = QListWidgetItem(f"👥  {g['name']}  ·  {g['game'] or 'cualquier juego'}\n"
                                 f"     Código: {g['code']}  ·  {members}")
            it.setData(Qt.ItemDataRole.UserRole, g["id"])
            self.glist.addItem(it)
            if g["id"] == cur_g:
                self.glist.setCurrentItem(it)
        self.glist.blockSignals(False)
        if cur_g and cur_g not in [g["id"] for g in self._groups]:
            self._chat_group = None
            self.chat.clear()
            self.chat_title.setText("Chat del grupo")

    @staticmethod
    def _current_id(lst: QListWidget):
        it = lst.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it else None

    # ------------------------------------------------------------------- cuenta
    def _creds(self):
        url, name, pw = self.server.text().strip(), self.username.text().strip(), self.password.text()
        if not url or len(name) < 3 or not pw:
            self.conn_msg.setText("Indica la dirección del servidor, tu nombre de usuario y tu contraseña.")
            return None
        self.ctx.settings.set("social.server_url", url)
        self.login_btn.setEnabled(False)
        self.join_btn.setEnabled(False)
        self.conn_msg.setText("Conectando…")
        return name, pw

    def _login(self) -> None:
        c = self._creds()
        if c:
            run_async(self.ctx.social.login, self._signed_in, self._sign_failed, *c)

    def _register(self) -> None:
        c = self._creds()
        if c:
            run_async(self.ctx.social.register, self._signed_in, self._sign_failed, *c)

    def _signed_in(self, _data) -> None:
        self.login_btn.setEnabled(True)
        self.join_btn.setEnabled(True)
        self.password.clear()
        self.conn_msg.setText("")
        self.notify("Sesión iniciada.")
        self.refresh()

    def _sign_failed(self, exc) -> None:
        self.login_btn.setEnabled(True)
        self.join_btn.setEnabled(True)
        self.conn_msg.setText(str(exc))

    def _logout(self) -> None:
        run_async(self.ctx.social.logout, lambda _: (self.notify("Sesión cerrada."), self.refresh()))

    def _copy_code(self) -> None:
        QGuiApplication.clipboard().setText(self.ctx.settings.get("social.friend_code", ""))
        self.notify("Código copiado al portapapeles.")

    def _status_changed(self) -> None:
        self.ctx.settings.set("social.status", self.status.currentData())
        self._load()

    # ------------------------------------------------------------------- amigos
    def _add_friend(self) -> None:
        code = self.code_in.text().strip()
        if code:
            run_async(self.ctx.social.add_friend, lambda f: (self.code_in.clear(), self._friend_added(f)),
                      lambda e: self.notify(str(e)), code)

    def _friend_added(self, f: dict) -> None:
        self.notify(f"{f['username']} añadido a tus amigos.")
        try:
            self.ctx.progress.record("friends_added")
            self.ctx.progress.log_activity("social", f"Añadiste a {f['username']} como amigo")
        except Exception:  # noqa: BLE001
            pass
        self._load()

    def _remove_friend(self) -> None:
        fid = self._current_id(self.flist)
        if fid and QMessageBox.question(self, "Eliminar amigo", "¿Seguro que quieres eliminar a este amigo?") == \
                QMessageBox.StandardButton.Yes:
            run_async(self.ctx.social.remove_friend, lambda _: self._load(), lambda e: self.notify(str(e)), fid)

    def _invite(self) -> None:
        fid = self._current_id(self.flist)
        if not fid:
            self.notify("Selecciona primero a un amigo.")
            return
        names = [g.name for g in self.ctx.db.list_games(order="played")]
        default = self.ctx.tracker.current_game_name()
        game, ok = (QInputDialog.getItem(self, "Invitar a jugar", "¿A qué juego?", names,
                                         max(0, names.index(default)) if default in names else 0, True)
                    if names else QInputDialog.getText(self, "Invitar a jugar", "¿A qué juego?"))
        if not ok or not game.strip():
            return
        run_async(self.ctx.social.invite, lambda _: self.notify("Invitación enviada."),
                  lambda e: self.notify(str(e)), fid, game.strip())

    # ------------------------------------------------------------------- grupos
    def _create_group(self) -> None:
        name, ok = QInputDialog.getText(self, "Nuevo grupo", "Nombre del grupo:")
        if not ok or not name.strip():
            return
        game, ok = QInputDialog.getText(self, "Nuevo grupo", "¿A qué jugaréis? (opcional):")
        if ok:
            run_async(self.ctx.social.create_group, lambda g: (self.notify(f"Grupo creado. Código: {g['code']}"),
                      self._load()), lambda e: self.notify(str(e)), name.strip(), game.strip())

    def _join_group(self) -> None:
        code, ok = QInputDialog.getText(self, "Unirse a un grupo", "Código del grupo:")
        if ok and code.strip():
            run_async(self.ctx.social.join_group, lambda g: (self.notify(f"Te has unido a «{g['name']}»."),
                      self._load()), lambda e: self.notify(str(e)), code)

    def _leave_group(self) -> None:
        gid = self._current_id(self.glist)
        if gid:
            run_async(self.ctx.social.leave_group, lambda _: self._load(), lambda e: self.notify(str(e)), gid)

    # --------------------------------------------------------------------- chat
    def _group_selected(self, *_args) -> None:
        gid = self._current_id(self.glist)
        if not gid or gid == self._chat_group:
            return
        self._chat_group, self._last_msg = gid, 0
        self.chat.clear()
        g = next((x for x in self._groups if x["id"] == gid), None)
        self.chat_title.setText(f"Chat · {g['name']}" if g else "Chat del grupo")
        self._poll_chat()

    def _poll_chat(self) -> None:
        if not self._chat_group or self._chat_busy or not self.ctx.social.registered:
            return
        self._chat_busy = True
        gid = self._chat_group
        run_async(self.ctx.social.messages, lambda msgs: self._append_messages(gid, msgs),
                  lambda e: setattr(self, "_chat_busy", False), gid, self._last_msg)

    def _append_messages(self, gid: int, msgs) -> None:
        self._chat_busy = False
        if gid != self._chat_group:
            return
        t = theme.current()
        me = self.ctx.settings.get("social.username", "")
        for m in msgs:
            self._last_msg = max(self._last_msg, m["id"])
            color = t["accent2"] if m["username"] == me else t["accent"]
            self.chat.append(f'<span style="color:{color}"><b>{html.escape(m["username"])}</b></span>: '
                             f'{html.escape(m["text"])}')

    def _send_chat(self) -> None:
        text = self.chat_in.text().strip()
        if not text or not self._chat_group:
            return
        self.chat_in.clear()
        run_async(self.ctx.social.send_message, lambda _: self._poll_chat(), lambda e: self.notify(str(e)),
                  self._chat_group, text)
