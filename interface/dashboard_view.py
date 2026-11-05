"""Inicio: resumen de actividad, continuar jugando y accesos rápidos."""
import getpass
from typing import Dict

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QListView, QListWidget, QListWidgetItem, QPushButton,
                               QScrollArea, QVBoxLayout, QWidget)

from core.platform_manager import LAUNCHERS_BY_KEY
from utils.helpers import format_duration, greeting
from .widgets import (BaseView, HBarChart, StatCard, card_frame, clear_layout, h1, h2, make_card_pixmap, muted)

W, H = 150, 210


class DashboardView(BaseView):
    def __init__(self, ctx):
        super().__init__(ctx)
        self._recent_ids: Dict[int, int] = {}

        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(18)

        self.hello = h1("Hola")
        self.sub = muted("Todos tus juegos. Una sola experiencia.", wrap=False)
        lay.addWidget(self.hello)
        lay.addWidget(self.sub)

        cards = QHBoxLayout()
        cards.setSpacing(14)
        self.c_today, self.c_week = StatCard("HOY"), StatCard("ESTA SEMANA")
        self.c_total, self.c_games = StatCard("TIEMPO TOTAL"), StatCard("BIBLIOTECA")
        for c in (self.c_today, self.c_week, self.c_total, self.c_games):
            cards.addWidget(c)
        lay.addLayout(cards)

        lay.addWidget(h2("Continuar jugando"))
        self.recent = QListWidget()
        self.recent.setObjectName("Grid")
        self.recent.setViewMode(QListView.ViewMode.IconMode)
        self.recent.setFlow(QListView.Flow.LeftToRight)
        self.recent.setWrapping(False)
        self.recent.setMovement(QListView.Movement.Static)
        self.recent.setIconSize(QSize(W, H))
        self.recent.setGridSize(QSize(W + 20, H + 20))
        self.recent.setFixedHeight(H + 42)
        self.recent.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.recent.itemActivated.connect(self._play_item)
        self.empty = muted("Aún no has jugado a nada desde Gamesword. Ve a la Biblioteca y pulsa JUGAR.")
        lay.addWidget(self.recent)
        lay.addWidget(self.empty)

        lay.addWidget(h2("Acceso rápido"))
        self.quick = QHBoxLayout()
        self.quick.setSpacing(10)
        lay.addLayout(self.quick)

        lay.addWidget(h2("Lo más jugado este mes"))
        box = card_frame()
        bl = QVBoxLayout(box)
        bl.setContentsMargins(20, 14, 20, 14)
        self.top = HBarChart()
        bl.addWidget(self.top)
        lay.addWidget(box)
        lay.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(inner)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll)

        ctx.tracker.session_finished.connect(self._on_session_finished)

    def _on_session_finished(self, game_id: int, name: str, seconds: int) -> None:
        self.refresh()

    def refresh(self) -> None:
        db = self.ctx.db
        name = self.ctx.settings.get("social.username") or getpass.getuser()
        self.hello.setText(f"{greeting()}, {name}")
        today = db.total_seconds(since=db.today_start())
        week = db.total_seconds(since=db.week_start())
        total = db.total_seconds()
        self.c_today.set(format_duration(today) if today else "0m", f"{db.session_count(1)} sesiones")
        self.c_week.set(format_duration(week) if week else "0m", "desde el lunes")
        self.c_total.set(format_duration(total) if total else "0m", f"{db.session_count()} sesiones")
        self.c_games.set(str(db.count_games()), f"{db.count_installed()} instalados")

        # Continuar jugando
        self.recent.clear()
        self._recent_ids.clear()
        recent = db.recent_games(10)
        for i, g in enumerate(recent):
            pm = make_card_pixmap(g.name, g.platform, g.cover_path, W, H, format_duration(g.total_seconds),
                                  bool(g.favorite), self.ctx.tracker.is_playing(g.id))
            it = QListWidgetItem(QIcon(pm), "")
            it.setSizeHint(QSize(W + 16, H + 16))
            it.setToolTip(g.name)
            self.recent.addItem(it)
            self._recent_ids[i] = g.id
            self.ctx.covers.request(g)
        self.recent.setVisible(bool(recent))
        self.empty.setVisible(not recent)

        # Accesos rápidos
        clear_layout(self.quick)
        keys = self.ctx.platforms.installed_keys()
        for k in keys:
            b = QPushButton(LAUNCHERS_BY_KEY[k].name)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, key=k: self.notify(self.ctx.platforms.open(key)[1]))
            self.quick.addWidget(b)
        if not keys:
            self.quick.addWidget(muted("No se ha detectado ningún lanzador. Mira la pestaña Lanzadores.", wrap=False))
        self.quick.addStretch()

        top = db.top_games(5, days=30)
        self.top.set_data([(n, s) for _, n, s in top], lambda s: format_duration(int(s)))

    def _play_item(self, item: QListWidgetItem) -> None:
        gid = self._recent_ids.get(self.recent.row(item))
        game = self.ctx.db.get_game(gid) if gid else None
        if game:
            self.notify(self.ctx.tracker.play(game)[1])
