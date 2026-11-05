"""Perfil: avatar, nivel, experiencia, insignias, desafíos, favoritos e historial de actividad."""
import getpass
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QMessageBox, QPushButton, QScrollArea, QVBoxLayout, QWidget)

from utils.helpers import format_duration, time_ago
from utils.paths import data_dir
from .widgets import (BaseView, GaugeBar, StatCard, card_frame, clear_layout, h1, h2, label, make_avatar, muted,
                      primary)


def _avatar_dir() -> Path:
    p = data_dir() / "avatars"
    p.mkdir(parents=True, exist_ok=True)
    return p


class ProfileDialog(QDialog):
    def __init__(self, parent, name: str, bio: str, avatar: str):
        super().__init__(parent)
        self.setWindowTitle("Editar perfil")
        self.setMinimumWidth(460)
        self.avatar_path = avatar
        self.preview = QLabel()
        self.preview.setFixedSize(96, 96)
        self.name = QLineEdit(name)
        self.name.setMaxLength(24)
        self.name.setPlaceholderText("Nombre de usuario")
        self.bio = QLineEdit(bio)
        self.bio.setMaxLength(120)
        self.bio.setPlaceholderText("Una frase sobre ti (opcional)")
        pick = QPushButton("Elegir avatar…")
        pick.clicked.connect(self._pick)
        reset = QPushButton("Quitar avatar")
        reset.clicked.connect(self._reset)
        ok, cancel = primary(QPushButton("Guardar")), QPushButton("Cancelar")
        ok.clicked.connect(self._accept)
        cancel.clicked.connect(self.reject)

        top = QHBoxLayout()
        top.addWidget(self.preview)
        col = QVBoxLayout()
        col.addWidget(pick)
        col.addWidget(reset)
        col.addStretch()
        top.addLayout(col)
        top.addStretch()
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(cancel)
        row.addWidget(ok)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 22)
        lay.setSpacing(12)
        lay.addWidget(h2("Editar perfil"))
        lay.addLayout(top)
        lay.addWidget(self.name)
        lay.addWidget(self.bio)
        lay.addLayout(row)
        self._refresh_preview()

    def _refresh_preview(self) -> None:
        self.preview.setPixmap(make_avatar(self.name.text() or "?", self.avatar_path, 96))

    def _pick(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Elegir avatar", "", "Imágenes (*.png *.jpg *.jpeg *.webp)")
        if not path:
            return
        img = QPixmap(path)
        if img.isNull():
            QMessageBox.warning(self, "Avatar", "No se pudo leer esa imagen.")
            return
        side = min(img.width(), img.height())
        square = img.copy((img.width() - side) // 2, (img.height() - side) // 2, side, side)
        square = square.scaled(256, 256, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        dest = _avatar_dir() / "avatar.png"
        if not square.save(str(dest), "PNG"):
            QMessageBox.warning(self, "Avatar", "No se pudo guardar el avatar.")
            return
        self.avatar_path = str(dest)
        self._refresh_preview()

    def _reset(self) -> None:
        self.avatar_path = ""
        self._refresh_preview()

    def _accept(self) -> None:
        if len(self.name.text().strip()) < 3:
            QMessageBox.warning(self, "Nombre", "El nombre debe tener al menos 3 caracteres.")
            return
        self.accept()


class ProfileView(BaseView):
    def __init__(self, ctx):
        super().__init__(ctx)
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(16)
        lay.addWidget(h1("Perfil"))

        head = card_frame()
        hl = QHBoxLayout(head)
        hl.setContentsMargins(22, 18, 22, 18)
        hl.setSpacing(18)
        self.avatar = QLabel()
        self.avatar.setFixedSize(96, 96)
        hl.addWidget(self.avatar)
        mid = QVBoxLayout()
        mid.setSpacing(4)
        self.name = label("", "H1")
        self.level = label("", "H2")
        self.bio = muted("", wrap=True)
        self.xp = GaugeBar("Experiencia")
        for w in (self.name, self.level, self.bio, self.xp):
            mid.addWidget(w)
        hl.addLayout(mid, 1)
        edit = primary(QPushButton("Editar perfil"))
        edit.clicked.connect(self._edit)
        hl.addWidget(edit, 0, Qt.AlignmentFlag.AlignTop)
        lay.addWidget(head)

        cards = QHBoxLayout()
        cards.setSpacing(14)
        self.c_time, self.c_level = StatCard("TIEMPO TOTAL JUGADO"), StatCard("NIVEL")
        self.c_ach, self.c_xp = StatCard("LOGROS"), StatCard("EXPERIENCIA TOTAL")
        for c in (self.c_time, self.c_level, self.c_ach, self.c_xp):
            cards.addWidget(c)
        lay.addLayout(cards)

        lay.addWidget(h2("Juegos favoritos"))
        self.fav_box = card_frame()
        self.fav_lay = QVBoxLayout(self.fav_box)
        self.fav_lay.setContentsMargins(20, 14, 20, 14)
        lay.addWidget(self.fav_box)

        lay.addWidget(h2("Desafíos"))
        self.ch_box = card_frame()
        self.ch_lay = QVBoxLayout(self.ch_box)
        self.ch_lay.setContentsMargins(20, 14, 20, 14)
        self.ch_lay.setSpacing(6)
        lay.addWidget(self.ch_box)

        self.badge_title = h2("Insignias")
        lay.addWidget(self.badge_title)
        self.badge_box = card_frame()
        self.badge_lay = QHBoxLayout(self.badge_box)
        self.badge_lay.setContentsMargins(20, 14, 20, 14)
        self.badge_lay.setSpacing(10)
        lay.addWidget(self.badge_box)

        lay.addWidget(h2("Historial de actividad"))
        self.activity = QListWidget()
        self.activity.setObjectName("List")
        self.activity.setMinimumHeight(240)
        lay.addWidget(self.activity)
        lay.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(inner)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll)

    # ------------------------------------------------------------------ datos
    def _profile(self):
        s = self.ctx.settings
        name = s.get("profile.username") or s.get("social.username") or getpass.getuser()
        return name, s.get("profile.bio", ""), s.get("profile.avatar", "")

    def refresh(self) -> None:
        self.ctx.progress.evaluate()
        snap = self.ctx.progress.snapshot()
        name, bio, avatar = self._profile()
        self.avatar.setPixmap(make_avatar(name, avatar, 96))
        self.name.setText(name)
        self.bio.setText(bio or "Sin descripción todavía. Pulsa «Editar perfil».")
        self.level.setText(f"Nivel {snap['level']}")
        pct = snap["xp_in_level"] * 100 / max(1, snap["xp_to_next"])
        self.xp.set_value(pct, f"{snap['xp_in_level']} / {snap['xp_to_next']} XP para el nivel {snap['level'] + 1}")
        self.c_time.set(format_duration(snap["playtime"]) if snap["playtime"] else "0m", "incluye horas importadas")
        self.c_level.set(str(snap["level"]), f"{snap['xp_to_next'] - snap['xp_in_level']} XP para subir")
        self.c_ach.set(f"{snap['unlocked']}/{len(snap['achievements'])}", "desbloqueados")
        self.c_xp.set(str(snap["xp"]), "10 XP por hora + recompensas")

        clear_layout(self.fav_lay)
        favs = self.ctx.db.list_games(favorites_only=True, order="played")[:5]
        if favs:
            for g in favs:
                self.fav_lay.addWidget(label(f"★  {g.name}   —   {format_duration(g.total_seconds)}"))
        else:
            self.fav_lay.addWidget(muted("Aún no tienes favoritos. Marca juegos con ★ en la Biblioteca.", wrap=False))
            for _, n, secs in snap["top_games"]:
                self.fav_lay.addWidget(muted(f"Más jugado: {n} ({format_duration(secs)})", wrap=False))

        clear_layout(self.ch_lay)
        for period, title in (("day", "Hoy"), ("week", "Esta semana")):
            self.ch_lay.addWidget(muted(title, wrap=False))
            for c in [x for x in snap["challenges"] if x["period"] == period]:
                bar = GaugeBar(f"{c['name']} — {c['desc']}")
                done = c["done"]
                bar.set_value(100 if done else min(100, c["value"] * 100 / max(1, c["target"])),
                              "✔ Completado" if done else f"{c['value']}/{c['target']} {c['unit']}  ·  +{c['xp']} XP")
                self.ch_lay.addWidget(bar)

        clear_layout(self.badge_lay)
        unlocked = [a for a in snap["achievements"] if a["unlocked_at"]]
        self.badge_title.setText(f"Insignias  ·  {len(unlocked)}")
        for a in unlocked:
            b = label(a["icon"])
            b.setStyleSheet("font-size: 28px;")
            b.setToolTip(f"{a['name']}: {a['desc']} (+{a['xp']} XP)")
            self.badge_lay.addWidget(b)
        if not unlocked:
            self.badge_lay.addWidget(muted("Desbloquea logros jugando y usando Gamesword.", wrap=False))
        self.badge_lay.addStretch()

        self.activity.clear()
        if not snap["activity"]:
            self.activity.addItem("Todavía no hay actividad. Abre un juego desde la Biblioteca.")
        for a in snap["activity"]:
            xp = f"   (+{a['xp']} XP)" if a["xp"] else ""
            self.activity.addItem(f"{time_ago(a['created_at'])}   ·   {a['text']}{xp}")

    def _edit(self) -> None:
        name, bio, avatar = self._profile()
        dlg = ProfileDialog(self, name, bio, avatar)
        if dlg.exec():
            s = self.ctx.settings
            s.set("profile.username", dlg.name.text().strip(), save=False)
            s.set("profile.bio", dlg.bio.text().strip(), save=False)
            s.set("profile.avatar", dlg.avatar_path)
            self.refresh()
