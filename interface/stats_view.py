"""Estadísticas: horas por día, ranking de juegos y logros."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QFrame, QGridLayout, QHBoxLayout, QScrollArea, QVBoxLayout, QWidget)

from utils.helpers import format_duration
from .widgets import (BarChart, BaseView, HBarChart, StatCard, card_frame, clear_layout, h1, h2, label, muted)

class StatsView(BaseView):
    def __init__(self, ctx):
        super().__init__(ctx)
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(16)

        head = QHBoxLayout()
        head.addWidget(h1("Estadísticas"))
        head.addStretch()
        self.range = QComboBox()
        for lab, days in (("Últimos 7 días", 7), ("Últimos 14 días", 14), ("Últimos 30 días", 30)):
            self.range.addItem(lab, days)
        self.range.currentIndexChanged.connect(self.refresh)
        head.addWidget(self.range)
        lay.addLayout(head)

        cards = QHBoxLayout()
        cards.setSpacing(14)
        self.c_time, self.c_sessions = StatCard("TIEMPO JUGADO"), StatCard("SESIONES")
        self.c_avg, self.c_fav = StatCard("MEDIA DIARIA"), StatCard("JUEGO DEL PERIODO")
        for c in (self.c_time, self.c_sessions, self.c_avg, self.c_fav):
            cards.addWidget(c)
        lay.addLayout(cards)

        lay.addWidget(h2("Horas por día"))
        box1 = card_frame()
        b1 = QVBoxLayout(box1)
        b1.setContentsMargins(18, 14, 18, 10)
        self.bars = BarChart()
        b1.addWidget(self.bars)
        lay.addWidget(box1)

        lay.addWidget(h2("Juegos más jugados"))
        box2 = card_frame()
        b2 = QVBoxLayout(box2)
        b2.setContentsMargins(20, 14, 20, 14)
        self.top = HBarChart()
        b2.addWidget(self.top)
        lay.addWidget(box2)

        self.ach_title = h2("Logros")
        lay.addWidget(self.ach_title)
        self.ach_grid = QGridLayout()
        self.ach_grid.setSpacing(10)
        lay.addLayout(self.ach_grid)
        lay.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(inner)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll)

    def refresh(self) -> None:
        db = self.ctx.db
        days = self.range.currentData() or 7
        by_day = db.seconds_by_day(days)
        total = sum(s for _, s in by_day)
        top = db.top_games(8, days=days)
        self.c_time.set(format_duration(total) if total else "0m", f"últimos {days} días")
        self.c_sessions.set(str(db.session_count(days)), "sesiones")
        self.c_avg.set(format_duration(total // days) if total else "0m", "por día")
        self.c_fav.set(top[0][1] if top else "—", format_duration(top[0][2]) if top else "")
        self.c_fav.value.setStyleSheet("font-size: 20px;")

        items = [((d[8:] + "/" + d[5:7]) if days > 7 else d[8:], s / 3600) for d, s in by_day]
        if days <= 7:
            names = ["L", "M", "X", "J", "V", "S", "D"]
            from datetime import date
            items = [(f"{names[date.fromisoformat(d).weekday()]} {d[8:]}", s / 3600) for d, s in by_day]
        self.bars.set_data(items, lambda v: f"{v:.1f}h" if v >= 0.1 else "<0.1h")
        self.top.set_data([(n, s) for _, n, s in top], lambda s: format_duration(int(s)))

        self.ctx.progress.evaluate()
        achievements = self.ctx.progress.snapshot()["achievements"]
        clear_layout(self.ach_grid)
        unlocked = 0
        for i, a in enumerate(achievements):
            ok = bool(a["unlocked_at"])
            unlocked += ok
            f = QFrame()
            f.setObjectName("BadgeOn" if ok else "Badge")
            l = QHBoxLayout(f)
            l.setContentsMargins(14, 10, 14, 10)
            ic = label(a["icon"] if ok else "🔒")
            ic.setStyleSheet("font-size: 24px;")
            tx = QVBoxLayout()
            tx.setSpacing(0)
            tx.addWidget(label(a["name"]))
            tx.addWidget(muted(f"{a['desc']}  ·  +{a['xp']} XP", wrap=True))
            l.addWidget(ic)
            l.addLayout(tx, 1)
            self.ach_grid.addWidget(f, i // 3, i % 3)
        for c in range(3):
            self.ach_grid.setColumnStretch(c, 1)
        self.ach_title.setText(f"Logros  ·  {unlocked}/{len(achievements)}")
