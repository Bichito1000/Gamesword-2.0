"""Biblioteca: rejilla de portadas, filtros, escaneo de juegos y detalle."""
from typing import Dict, Optional

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QComboBox, QFileDialog, QHBoxLayout, QLineEdit, QListView, QListWidget,
                               QListWidgetItem, QMenu, QMessageBox, QPushButton, QVBoxLayout, QInputDialog)

from core import game_detector, library_sync
from core.models import Game
from utils.helpers import format_duration, open_in_explorer, time_ago
from utils.qt_async import run_async
from .dialogs import GameDialog
from .widgets import (BaseView, PLATFORM_LABELS, card_frame, h1, label, make_card_pixmap, muted, primary)

CARD_W, CARD_H = 190, 266            # tamaño normal
COMPACT_W, COMPACT_H = 150, 210      # modo compacto


class LibraryView(BaseView):
    def __init__(self, ctx):
        super().__init__(ctx)
        self.cw, self.ch = self._card_size()
        self._items: Dict[int, QListWidgetItem] = {}
        self._games: Dict[int, Game] = {}
        self._scanning = False

        self.title = h1("Biblioteca")
        self.count = muted("", wrap=False)
        self.search = QLineEdit()
        self.search.setPlaceholderText("🔍  Buscar por nombre o etiqueta…")
        self.search.setMinimumWidth(240)
        self.platform = QComboBox()
        self.platform.addItem("Todas las plataformas", "all")
        for k, v in PLATFORM_LABELS.items():
            self.platform.addItem(v, k)
        self.coll = QComboBox()
        self.coll.setMinimumWidth(170)
        self.coll_btn = QPushButton("🗂 Colecciones")
        self.state = QComboBox()
        for lab, key in (("Todos los juegos", None), ("Instalados", True), ("No instalados", False)):
            self.state.addItem(lab, key)
        self.sort = QComboBox()
        for lab, key in (("Nombre", "name"), ("Más jugados", "played"), ("Recientes", "recent"), ("Añadidos", "added")):
            self.sort.addItem(lab, key)
        self.fav = QPushButton("★ Favoritos")
        self.fav.setProperty("chip", True)
        self.fav.setCheckable(True)
        self.scan_btn = QPushButton("⟳  Sincronizar bibliotecas")
        self.folder_btn = QPushButton("📁 Carpeta…")
        self.add_btn = primary(QPushButton("+  Añadir juego"))

        top = QHBoxLayout()
        top.setSpacing(10)
        top.addWidget(self.title)
        top.addWidget(self.count)
        top.addStretch()
        top.addWidget(self.scan_btn)
        top.addWidget(self.folder_btn)
        top.addWidget(self.add_btn)

        filters = QHBoxLayout()
        filters.setSpacing(10)
        filters.addWidget(self.search, 1)
        filters.addWidget(self.coll)
        filters.addWidget(self.coll_btn)
        filters.addWidget(self.platform)
        filters.addWidget(self.state)
        filters.addWidget(self.sort)
        filters.addWidget(self.fav)

        self.grid = QListWidget()
        self.grid.setObjectName("Grid")
        self.grid.setViewMode(QListView.ViewMode.IconMode)
        self.grid.setResizeMode(QListView.ResizeMode.Adjust)
        self.grid.setMovement(QListView.Movement.Static)
        self.grid.setIconSize(QSize(self.cw, self.ch))
        self.grid.setGridSize(QSize(self.cw + 22, self.ch + 22))
        self.grid.setSpacing(4)
        self.grid.setUniformItemSizes(True)
        self.grid.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.grid.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)

        # Barra de detalle
        self.detail = card_frame()
        d = QHBoxLayout(self.detail)
        d.setContentsMargins(20, 14, 20, 14)
        info = QVBoxLayout()
        info.setSpacing(2)
        self.d_name = label("Selecciona un juego", "H2")
        self.d_meta = muted("Doble clic para jugar · clic derecho para más opciones", wrap=False)
        info.addWidget(self.d_name)
        info.addWidget(self.d_meta)
        d.addLayout(info, 1)
        self.d_fav = QPushButton("☆")
        self.d_fav.setFixedWidth(46)
        self.d_edit = QPushButton("Editar")
        self.d_play = primary(QPushButton("▶  JUGAR"))
        self.d_play.setMinimumWidth(130)
        for b in (self.d_fav, self.d_edit, self.d_play):
            b.setEnabled(False)
            d.addWidget(b)

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 20)
        root.setSpacing(14)
        root.addLayout(top)
        root.addLayout(filters)
        root.addWidget(self.grid, 1)
        root.addWidget(self.detail)

        self.search.textChanged.connect(self.refresh)
        self.platform.currentIndexChanged.connect(self.refresh)
        self.state.currentIndexChanged.connect(self.refresh)
        self.coll.currentIndexChanged.connect(self.refresh)
        self.coll_btn.clicked.connect(self._collections_menu)
        self.sort.currentIndexChanged.connect(self.refresh)
        self.fav.toggled.connect(self.refresh)
        self.add_btn.clicked.connect(self.add_game)
        self.scan_btn.clicked.connect(self.scan)
        self.folder_btn.clicked.connect(self.scan_folder)
        self.grid.itemSelectionChanged.connect(self._update_detail)
        self.grid.itemActivated.connect(lambda it: self.play(self._id(it)))   # doble clic, Enter o botón A
        self.grid.customContextMenuRequested.connect(self._menu)
        self.d_play.clicked.connect(lambda: self.play(self._selected_id()))
        self.d_edit.clicked.connect(lambda: self.edit(self._selected_id()))
        self.d_fav.clicked.connect(lambda: self.toggle_fav(self._selected_id()))

        ctx.covers.cover_ready.connect(self._cover_ready)
        # Métodos enlazados (no lambdas): así Qt entrega la señal del hilo de seguimiento en el hilo de la interfaz
        ctx.tracker.session_started.connect(self._on_session_started)
        ctx.tracker.session_finished.connect(self._on_session_finished)

    # ------------------------------------------------------------ utilidades
    def _card_size(self):
        return (COMPACT_W, COMPACT_H) if self.ctx.settings.get("app.compact") else (CARD_W, CARD_H)

    def apply_compact(self) -> None:
        """Reajusta el tamaño de las portadas cuando cambia el modo compacto."""
        self.cw, self.ch = self._card_size()
        self.grid.setIconSize(QSize(self.cw, self.ch))
        self.grid.setGridSize(QSize(self.cw + 22, self.ch + 22))
        self.refresh()

    def _record(self, counter: str) -> None:
        try:
            self.ctx.progress.record(counter)
        except Exception:  # noqa: BLE001
            pass

    @staticmethod
    def _id(item: Optional[QListWidgetItem]) -> Optional[int]:
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _selected_id(self) -> Optional[int]:
        sel = self.grid.selectedItems()
        return self._id(sel[0]) if sel else None

    def _icon_for(self, g: Game) -> QIcon:
        sub = format_duration(g.total_seconds) if g.total_seconds else "Sin jugar"
        pm = make_card_pixmap(g.name, g.platform, g.cover_path, self.cw, self.ch,
                              sub if g.installed else (sub if g.total_seconds else "En tu cuenta"),
                              bool(g.favorite), self.ctx.tracker.is_playing(g.id), bool(g.installed))
        return QIcon(pm)

    # --------------------------------------------------------------- refresco
    def _reload_collections(self) -> None:
        current = self.coll.currentData()
        self.coll.blockSignals(True)
        self.coll.clear()
        self.coll.addItem("Todas las colecciones", None)
        for cid, name, n in self.ctx.db.list_collections():
            self.coll.addItem(f"{name}  ({n})", cid)
        idx = self.coll.findData(current)
        self.coll.setCurrentIndex(idx if idx >= 0 else 0)
        self.coll.blockSignals(False)

    def refresh(self) -> None:
        self._reload_collections()
        keep = self._selected_id()
        games = self.ctx.db.list_games(self.search.text().strip(), self.platform.currentData(),
                                       self.fav.isChecked(), self.sort.currentData(), self.state.currentData(),
                                       self.coll.currentData())
        self.grid.blockSignals(True)
        self.grid.clear()
        self._items.clear()
        self._games = {g.id: g for g in games}
        for g in games:
            it = QListWidgetItem(self._icon_for(g), "")
            it.setData(Qt.ItemDataRole.UserRole, g.id)
            it.setSizeHint(QSize(self.cw + 18, self.ch + 18))
            it.setToolTip(f"{g.name}\n{PLATFORM_LABELS.get(g.platform, g.platform)} · "
                          f"{format_duration(g.total_seconds)} jugadas")
            self.grid.addItem(it)
            self._items[g.id] = it
            self.ctx.covers.request(g)
        if keep in self._items:
            self._items[keep].setSelected(True)
        self.grid.blockSignals(False)
        total, inst = self.ctx.db.count_games(), self.ctx.db.count_installed()
        self.count.setText((f"{len(games)} de {total} juegos" if len(games) != total else f"{total} juegos")
                           + f"  ·  {inst} instalados")
        self._update_detail()

    def _on_session_started(self, game_id: int, name: str) -> None:
        self._refresh_icons()
        self._update_detail()

    def _on_session_finished(self, game_id: int, name: str, seconds: int) -> None:
        self.refresh()

    def _refresh_icons(self) -> None:
        for gid, it in self._items.items():
            g = self._games.get(gid)
            if g:
                it.setIcon(self._icon_for(g))

    def _cover_ready(self, game_id: int, path: str) -> None:
        g, it = self._games.get(game_id), self._items.get(game_id)
        if g and it:
            g.cover_path = path
            it.setIcon(self._icon_for(g))

    def _update_detail(self) -> None:
        gid = self._selected_id()
        g = self._games.get(gid) if gid else None
        for b in (self.d_fav, self.d_edit, self.d_play):
            b.setEnabled(g is not None)
        if not g:
            self.d_name.setText("Selecciona un juego")
            self.d_meta.setText("Doble clic para jugar · clic derecho para más opciones")
            self.d_fav.setText("☆")
            return
        self.d_name.setText(g.name)
        state = "" if g.installed else "  ·  no instalado"
        self.d_meta.setText(f"{PLATFORM_LABELS.get(g.platform, g.platform)}{state}  ·  "
                            f"{format_duration(g.total_seconds)} jugadas  ·  {g.sessions} sesiones  ·  "
                            f"última vez: {time_ago(g.last_played)}")
        self.d_fav.setText("★" if g.favorite else "☆")
        self.d_play.setText("● En ejecución" if self.ctx.tracker.is_playing(g.id)
                            else ("▶  JUGAR" if g.installed else "⬇  INSTALAR"))

    # --------------------------------------------------------------- acciones
    def play(self, game_id: Optional[int]) -> None:
        g = self._games.get(game_id) if game_id else None
        if not g:
            return
        ok, msg = self.ctx.tracker.play(g)
        self.notify(msg)
        if not ok and "no tiene" in msg:
            self.edit(game_id)

    def toggle_fav(self, game_id: Optional[int]) -> None:
        if game_id:
            self.ctx.db.toggle_favorite(game_id)
            self.refresh()

    def add_game(self) -> None:
        dlg = GameDialog(self)
        if dlg.exec():
            g = dlg.result_game()
            g.id = self.ctx.db.add_game(g)
            self.notify(f"«{g.name}» añadido a tu biblioteca.")
            self.refresh()

    def edit(self, game_id: Optional[int]) -> None:
        g = self._games.get(game_id) if game_id else None
        if not g:
            return
        dlg = GameDialog(self, g)
        if dlg.exec():
            self.ctx.db.update_game(dlg.result_game())
            self.refresh()

    def delete(self, game_id: Optional[int]) -> None:
        g = self._games.get(game_id) if game_id else None
        if not g:
            return
        box = QMessageBox.question(self, "Quitar juego",
                                   f"¿Quitar «{g.name}» de la biblioteca?\nNo se borra nada de tu disco.")
        if box == QMessageBox.StandardButton.Yes:
            self.ctx.db.delete_game(g.id)
            self.refresh()

    def _new_collection(self, add_game_id: Optional[int] = None) -> None:
        name, ok = QInputDialog.getText(self, "Nueva colección", "Nombre de la colección:")
        if not ok:
            return
        try:
            cid = self.ctx.db.create_collection(name)
        except ValueError as exc:
            QMessageBox.warning(self, "Colección", str(exc))
            return
        if add_game_id:
            self.ctx.db.set_in_collection(cid, add_game_id, True)
        self._record("collections_created")
        self.refresh()

    def _collections_menu(self) -> None:
        m = QMenu(self)
        a_new = m.addAction("＋  Nueva colección…")
        cid = self.coll.currentData()
        a_ren = m.addAction("✎  Renombrar la colección actual…")
        a_del = m.addAction("🗑  Eliminar la colección actual")
        a_ren.setEnabled(bool(cid))
        a_del.setEnabled(bool(cid))
        chosen = m.exec(self.coll_btn.mapToGlobal(self.coll_btn.rect().bottomLeft()))
        if chosen == a_new:
            self._new_collection()
        elif chosen == a_ren and cid:
            name, ok = QInputDialog.getText(self, "Renombrar colección", "Nuevo nombre:")
            if ok:
                try:
                    self.ctx.db.rename_collection(cid, name)
                except ValueError as exc:
                    QMessageBox.warning(self, "Colección", str(exc))
                self.refresh()
        elif chosen == a_del and cid:
            if QMessageBox.question(self, "Eliminar colección", "¿Eliminar esta colección? Los juegos no se borran.") \
                    == QMessageBox.StandardButton.Yes:
                self.ctx.db.delete_collection(cid)
                self.coll.setCurrentIndex(0)
                self.refresh()

    def _menu(self, pos) -> None:
        item = self.grid.itemAt(pos)
        if not item:
            return
        gid = self._id(item)
        g = self._games[gid]
        m = QMenu(self)
        a_play = m.addAction("▶  Jugar")
        a_fav = m.addAction("☆  Quitar de favoritos" if g.favorite else "★  Añadir a favoritos")
        a_edit = m.addAction("✎  Editar…")
        a_dir = m.addAction("📂  Abrir carpeta")
        sub = m.addMenu("🗂  Colecciones")
        member = self.ctx.db.collections_of_game(gid)
        coll_actions = {}
        for cid, cname, _n in self.ctx.db.list_collections():
            act = sub.addAction(cname)
            act.setCheckable(True)
            act.setChecked(cid in member)
            coll_actions[act] = cid
        if coll_actions:
            sub.addSeparator()
        a_newcoll = sub.addAction("＋  Nueva colección con este juego…")
        m.addSeparator()
        a_del = m.addAction("🗑  Quitar de la biblioteca")
        chosen = m.exec(self.grid.viewport().mapToGlobal(pos))
        if chosen == a_play:
            self.play(gid)
        elif chosen == a_fav:
            self.toggle_fav(gid)
        elif chosen == a_edit:
            self.edit(gid)
        elif chosen == a_dir:
            target = g.install_dir or g.exe_path
            if target:
                open_in_explorer(target)
            else:
                self.notify("Este juego no tiene carpeta configurada.")
        elif chosen == a_del:
            self.delete(gid)
        elif chosen == a_newcoll:
            self._new_collection(gid)
        elif chosen in coll_actions:
            self.ctx.db.set_in_collection(coll_actions[chosen], gid, chosen.isChecked())
            self.refresh()

    # ----------------------------------------------------------------- escaneo
    def scan(self, silent: bool = False) -> None:
        """Sincroniza instalados + todo lo que posees en tus cuentas. `silent` omite el resumen emergente."""
        if self._scanning:
            return
        self._scanning = True
        self.scan_btn.setEnabled(False)
        self.scan_btn.setText("Sincronizando…")
        self.notify("Sincronizando tus bibliotecas…")

        def work():
            return library_sync.sync_all(self.ctx.db, self.ctx.settings)

        def done(lines):
            self._scan_finished(lines, silent)

        run_async(work, done, lambda e: self._scan_finished([f"Error al sincronizar: {e}"], silent))

    def _scan_finished(self, lines, silent: bool) -> None:
        self._scanning = False
        self.scan_btn.setEnabled(True)
        self.scan_btn.setText("⟳  Sincronizar bibliotecas")
        self.notify(lines[0] if lines else "Sincronización completa.")
        if not (lines and lines[0].startswith("Error")):
            self._record("syncs")
        self.refresh()
        if not silent:
            QMessageBox.information(self, "Sincronización de bibliotecas", "\n\n".join(lines))

    def scan_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Carpeta que contiene tus juegos (una subcarpeta por juego)")
        if not folder:
            return
        self.notify("Escaneando carpeta…")

        def work():
            found = game_detector.scan_folder(folder)
            return len(found), self.ctx.db.upsert_detected(found)

        run_async(work, lambda r: (self.notify(f"Carpeta analizada: {r[0]} juegos encontrados, {r[1]} nuevos."),
                                   self.refresh()),
                  lambda e: self.notify(f"Error: {e}"))
