"""Lanzadores: abrir Steam, Epic, Ubisoft, EA, GOG, Battle.net, Rockstar y Discord."""
import webbrowser

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (QFileDialog, QFrame, QGridLayout, QHBoxLayout, QPushButton, QScrollArea,
                               QVBoxLayout, QWidget)

from core.platform_manager import LAUNCHERS
from utils.qt_async import run_async
from .widgets import BaseView, PLATFORM_COLORS, clear_layout, h1, h2, label, muted, primary


class LauncherView(BaseView):
    def __init__(self, ctx):
        super().__init__(ctx)
        self._running = set()
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(14)
        head = QHBoxLayout()
        head.addWidget(h1("Lanzadores"))
        head.addStretch()
        reload_btn = QPushButton("⟳  Actualizar")
        reload_btn.clicked.connect(self.refresh)
        head.addWidget(reload_btn)
        lay.addLayout(head)
        lay.addWidget(muted("Abre tus plataformas desde un único sitio. Si alguna no se detecta, indica su "
                            "ejecutable con «Ruta…». Gamesword nunca te pide contraseñas."))
        self.grid = QGridLayout()
        self.grid.setSpacing(14)
        lay.addLayout(self.grid)
        lay.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(inner)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll)

        self.timer = QTimer(self)
        self.timer.setInterval(6000)
        self.timer.timeout.connect(self._poll_running)

    def showEvent(self, e):
        super().showEvent(e)
        self.timer.start()

    def hideEvent(self, e):
        super().hideEvent(e)
        self.timer.stop()

    def _poll_running(self) -> None:
        run_async(self.ctx.platforms.running_keys, self._set_running)

    def _set_running(self, running) -> None:
        if running != self._running:
            self._running = running
            self._build()

    def refresh(self) -> None:
        self._poll_running()
        self._build()

    def _build(self) -> None:
        clear_layout(self.grid)
        for i, info in enumerate(LAUNCHERS):
            installed = self.ctx.platforms.is_installed(info.key)
            running = info.key in self._running
            card = QFrame()
            card.setObjectName("Card")
            color = PLATFORM_COLORS.get(info.key, "#8b5cf6")
            card.setStyleSheet(f"QFrame#Card {{ border-top: 3px solid {color}; }}")
            v = QVBoxLayout(card)
            v.setContentsMargins(20, 18, 20, 16)
            v.setSpacing(6)
            v.addWidget(h2(info.name))
            if running:
                st = label("● En ejecución", "Success")
            elif installed:
                st = label("✔ Instalado", "Success")
            else:
                st = label("✖ No encontrado", "Danger")
            v.addWidget(st)
            v.addStretch()
            row = QHBoxLayout()
            row.setSpacing(8)
            if installed or info.uri:
                b = primary(QPushButton("Abrir"))
                b.clicked.connect(lambda _=False, k=info.key: self.notify(self.ctx.platforms.open(k)[1]))
                row.addWidget(b)
            if not installed and info.download_url:
                d = QPushButton("Descargar")
                d.clicked.connect(lambda _=False, u=info.download_url: webbrowser.open(u))
                row.addWidget(d)
            p = QPushButton("Ruta…")
            p.setToolTip("Indicar manualmente el ejecutable")
            p.clicked.connect(lambda _=False, k=info.key: self._pick(k))
            row.addWidget(p)
            v.addLayout(row)
            self.grid.addWidget(card, i // 3, i % 3)
        for c in range(3):
            self.grid.setColumnStretch(c, 1)

    def _pick(self, key: str) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Elegir ejecutable", "", "Ejecutables (*.exe);;Todos (*)")
        if path:
            self.ctx.platforms.set_custom_path(key, path)
            self.notify("Ruta guardada.")
            self._build()
