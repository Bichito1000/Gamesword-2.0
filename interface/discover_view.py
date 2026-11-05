"""Descubrir: recomendaciones personalizadas y por categorías."""
import webbrowser
from typing import Dict, List
from urllib.parse import quote

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QHBoxLayout, QLineEdit, QListView, QListWidget, QListWidgetItem, QPushButton,
                               QScrollArea, QVBoxLayout, QWidget)

from ai.catalog import CATALOG
from ai.recommendations import by_tags, find_in_catalog, for_user, similar_to
from core.covers import covers_dir
from .widgets import BaseView, card_frame, h1, h2, label, make_card_pixmap, muted, primary

CATEGORIES = [("Para ti", None), ("Cooperativo", "cooperativo"), ("Mundo abierto", "mundo abierto"),
              ("Terror", "terror"), ("Shooter", "shooter"), ("RPG", "rpg"), ("Supervivencia", "supervivencia"),
              ("Indie", "indie"), ("Estrategia", "estrategia"), ("Carreras", "carreras"),
              ("Puzzle", "puzzle"), ("Plataformas", "plataformas"), ("Todo el catálogo", "__all__")]
CW, CH = 170, 238


class DiscoverView(BaseView):
    def __init__(self, ctx):
        super().__init__(ctx)
        self._entries: List[dict] = []
        self._items: Dict[int, QListWidgetItem] = {}
        self._current = "Para ti"

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 20)
        root.setSpacing(12)
        head = QHBoxLayout()
        head.addWidget(h1("Descubrir"))
        head.addStretch()
        self.search = QLineEdit()
        self.search.setPlaceholderText("🔍  Buscar en el catálogo…")
        self.search.setMinimumWidth(260)
        self.search.textChanged.connect(self._search)
        head.addWidget(self.search)
        root.addLayout(head)

        self.chips = []
        chip_row = QHBoxLayout()
        chip_row.setSpacing(8)
        for lab, tag in CATEGORIES:
            b = QPushButton(lab)
            b.setProperty("chip", True)
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, l=lab, t=tag: self._choose(l, t))
            chip_row.addWidget(b)
            self.chips.append((lab, b))
        chip_row.addStretch()
        holder = QWidget()
        holder.setLayout(chip_row)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setWidget(holder)
        sc.setFixedHeight(54)
        sc.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        root.addWidget(sc)

        self.caption = muted("", wrap=False)
        root.addWidget(self.caption)
        self.grid = QListWidget()
        self.grid.setObjectName("Grid")
        self.grid.setViewMode(QListView.ViewMode.IconMode)
        self.grid.setResizeMode(QListView.ResizeMode.Adjust)
        self.grid.setMovement(QListView.Movement.Static)
        self.grid.setIconSize(QSize(CW, CH))
        self.grid.setGridSize(QSize(CW + 22, CH + 22))
        self.grid.setUniformItemSizes(True)
        self.grid.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.grid.itemSelectionChanged.connect(self._show_detail)
        root.addWidget(self.grid, 1)

        self.detail = card_frame()
        d = QHBoxLayout(self.detail)
        d.setContentsMargins(20, 14, 20, 14)
        info = QVBoxLayout()
        info.setSpacing(2)
        self.d_name = label("Selecciona un juego para ver detalles", "H2")
        self.d_meta = muted("", wrap=True)
        info.addWidget(self.d_name)
        info.addWidget(self.d_meta)
        d.addLayout(info, 1)
        self.d_similar = QPushButton("Ver parecidos")
        self.d_store = primary(QPushButton("Abrir en la tienda"))
        for b in (self.d_similar, self.d_store):
            b.setEnabled(False)
            d.addWidget(b)
        self.d_similar.clicked.connect(self._similar)
        self.d_store.clicked.connect(self._store)
        root.addWidget(self.detail)

        ctx.covers.appid_cover_ready.connect(self._cover_ready)

    # ------------------------------------------------------------------ datos
    def refresh(self) -> None:
        self._choose(self._current, dict(CATEGORIES).get(self._current))

    def _choose(self, label_text: str, tag) -> None:
        self._current = label_text
        for lab, b in self.chips:
            b.setChecked(lab == label_text)
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        owned = [g.name for g in self.ctx.db.list_games(order="played")]
        if tag is None:
            entries = for_user(self.ctx.db.list_games(order="played"), 24)
            self.caption.setText("Elegidos según los juegos que más usas")
        elif tag == "__all__":
            entries = [dict(e, reason="") for e in sorted(CATALOG, key=lambda e: e["name"])]
            self.caption.setText(f"{len(entries)} juegos en el catálogo")
        else:
            entries = by_tags([tag], 40, owned)
            self.caption.setText(f"{len(entries)} juegos de «{label_text}» que aún no tienes en la biblioteca")
        self._show(entries)

    def _search(self, text: str) -> None:
        q = text.strip().lower()
        if not q:
            self.refresh()
            return
        for _, b in self.chips:
            b.setChecked(False)
        entries = [dict(e, reason="") for e in CATALOG if q in e["name"].lower() or any(q in t for t in e["tags"])]
        self.caption.setText(f"{len(entries)} resultados")
        self._show(entries)

    def _show(self, entries: List[dict]) -> None:
        self._entries = entries
        self._items.clear()
        self.grid.blockSignals(True)
        self.grid.clear()
        for i, e in enumerate(entries):
            it = QListWidgetItem(self._icon(e), "")
            it.setData(Qt.ItemDataRole.UserRole, i)
            it.setSizeHint(QSize(CW + 18, CH + 18))
            it.setToolTip(e["name"])
            self.grid.addItem(it)
            if e.get("appid"):
                self._items.setdefault(e["appid"], it)
                self.ctx.covers.request_appid(e["appid"])
        self.grid.blockSignals(False)
        self._show_detail()

    def _icon(self, e: dict) -> QIcon:
        path = ""
        if e.get("appid"):
            p = covers_dir() / f"steam_{e['appid']}.jpg"
            path = str(p) if p.exists() else ""
        tag = "co-op" if e["coop"] else ""
        return QIcon(make_card_pixmap(e["name"], "other", path, CW, CH, f"{e['year']}  {tag}".strip()))

    def _cover_ready(self, appid: int, _path: str) -> None:
        it = self._items.get(appid)
        if it is not None:
            e = self._entries[it.data(Qt.ItemDataRole.UserRole)]
            it.setIcon(self._icon(e))

    # ---------------------------------------------------------------- detalle
    def _selected(self):
        sel = self.grid.selectedItems()
        return self._entries[sel[0].data(Qt.ItemDataRole.UserRole)] if sel else None

    def _show_detail(self) -> None:
        e = self._selected()
        for b in (self.d_similar, self.d_store):
            b.setEnabled(e is not None)
        if not e:
            self.d_name.setText("Selecciona un juego para ver detalles")
            self.d_meta.setText("")
            return
        self.d_name.setText(f"{e['name']}  ({e['year']})")
        reason = f"  ·  {e['reason']}" if e.get("reason") else ""
        self.d_meta.setText(", ".join(e["tags"]) + (" · cooperativo" if e["coop"] else "") + reason)

    def _store(self) -> None:
        e = self._selected()
        if e:
            url = (f"https://store.steampowered.com/app/{e['appid']}" if e.get("appid")
                   else f"https://store.steampowered.com/search/?term={quote(e['name'])}")
            webbrowser.open(url)

    def _similar(self) -> None:
        e = self._selected()
        if not e:
            return
        owned = [g.name for g in self.ctx.db.list_games()]
        self.caption.setText(f"Juegos parecidos a {e['name']}")
        for _, b in self.chips:
            b.setChecked(False)
        self._show(similar_to(find_in_catalog(e["name"]) or e, 16, owned))
