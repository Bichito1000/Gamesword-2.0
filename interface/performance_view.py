"""Rendimiento: CPU, RAM y GPU en vivo, y «modo gaming» (cerrar apps pesadas / plan de energía)."""
import psutil
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (QHBoxLayout, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QScrollArea,
                               QVBoxLayout, QWidget)

from core import system_monitor as sm
from utils.qt_async import run_async
from .widgets import BaseView, GaugeBar, card_frame, h1, h2, muted, primary


class PerformanceView(BaseView):
    def __init__(self, ctx):
        super().__init__(ctx)
        self._busy = False
        self._prev_plan = None
        psutil.cpu_percent(interval=None)       # la primera lectura siempre es 0

        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(16)
        lay.addWidget(h1("Rendimiento"))
        self.playing = muted("", wrap=False)
        lay.addWidget(self.playing)

        live = card_frame()
        ll = QVBoxLayout(live)
        ll.setContentsMargins(22, 16, 22, 16)
        ll.setSpacing(6)
        self.cpu, self.ram = GaugeBar("CPU"), GaugeBar("Memoria RAM")
        self.gpu, self.vram = GaugeBar("GPU"), GaugeBar("Memoria de vídeo (VRAM)")
        for g in (self.cpu, self.ram, self.gpu, self.vram):
            ll.addWidget(g)
        self.gpu_note = muted("", wrap=True)
        ll.addWidget(self.gpu_note)
        ll.addWidget(muted("Gamesword no puede medir los FPS: hacerlo exige inyectarse en el juego, y los "
                           "anti-trampas lo bloquean. Para FPS usa el overlay de Steam, GeForce Experience o "
                           "MSI Afterburner.", wrap=True))
        lay.addWidget(live)

        lay.addWidget(h2("Modo gaming"))
        box = card_frame()
        bl = QVBoxLayout(box)
        bl.setContentsMargins(22, 16, 22, 16)
        bl.setSpacing(10)
        bl.addWidget(muted("Programas que más memoria consumen. Cierra los que no necesites antes de jugar. "
                           "Gamesword nunca cierra nada por su cuenta y protege los procesos del sistema.", wrap=True))
        self.procs = QListWidget()
        self.procs.setObjectName("List")
        self.procs.setMinimumHeight(220)
        bl.addWidget(self.procs)
        row = QHBoxLayout()
        reload_btn = QPushButton("Actualizar lista")
        reload_btn.clicked.connect(self._load_procs)
        close_btn = QPushButton("Cerrar seleccionado")
        close_btn.setProperty("danger", True)
        close_btn.clicked.connect(self._close_selected)
        row.addWidget(reload_btn)
        row.addWidget(close_btn)
        row.addStretch()
        bl.addLayout(row)
        lay.addWidget(box)

        lay.addWidget(h2("Plan de energía de Windows"))
        pw = card_frame()
        pl = QHBoxLayout(pw)
        pl.setContentsMargins(22, 16, 22, 16)
        self.plan_msg = muted("Usa el plan «Alto rendimiento» mientras juegas y restaura el anterior después.",
                              wrap=True)
        high = primary(QPushButton("Activar Alto rendimiento"))
        high.clicked.connect(self._high)
        back = QPushButton("Restaurar plan anterior")
        back.clicked.connect(self._restore)
        pl.addWidget(self.plan_msg, 1)
        pl.addWidget(back)
        pl.addWidget(high)
        lay.addWidget(pw)
        lay.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(inner)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll)

        self.timer = QTimer(self)
        self.timer.setInterval(1500)
        self.timer.timeout.connect(self._tick)

    def showEvent(self, e):
        super().showEvent(e)
        self.timer.start()

    def hideEvent(self, e):
        super().hideEvent(e)
        self.timer.stop()

    def refresh(self) -> None:
        name = self.ctx.tracker.current_game_name()
        self.playing.setText(f"Ahora mismo estás jugando a {name}." if name else "No hay ningún juego en marcha.")
        self._tick()
        self._load_procs()

    # --------------------------------------------------------------- en vivo
    def _tick(self) -> None:
        if self._busy:
            return
        self._busy = True
        run_async(sm.snapshot, self._show, lambda e: setattr(self, "_busy", False))

    def _show(self, s) -> None:
        self._busy = False
        self.cpu.set_value(s["cpu"], f"{s['cpu']:.0f} %")
        self.ram.set_value(s["ram"], f"{s['ram_used']:.1f} / {s['ram_total']:.1f} GB  ({s['ram']:.0f} %)")
        g = s["gpu"]
        if g:
            self.gpu.set_value(g["util"], f"{g['util']:.0f} %  ·  {g['temp']:.0f} °C  ·  {g['name']}")
            pct = g["mem_used"] * 100 / g["mem_total"] if g["mem_total"] else 0
            self.vram.set_value(pct, f"{g['mem_used']:.0f} / {g['mem_total']:.0f} MB")
            self.gpu_note.setText("")
        else:
            self.gpu.set_value(0, "no disponible")
            self.vram.set_value(0, "no disponible")
            self.gpu_note.setText("Solo se pueden medir GPUs NVIDIA (necesita nvidia-smi, incluido en sus drivers).")

    # ---------------------------------------------------------- modo gaming
    def _load_procs(self) -> None:
        run_async(sm.top_processes, self._fill, None, 12)

    def _fill(self, rows) -> None:
        self.procs.clear()
        for r in rows:
            n = len(r["pids"])
            it = QListWidgetItem(f"{r['name']}   —   {r['mb']:.0f} MB" + (f"   ({n} procesos)" if n > 1 else ""))
            it.setData(Qt.ItemDataRole.UserRole, (r["name"], r["pids"]))
            self.procs.addItem(it)

    def _close_selected(self) -> None:
        it = self.procs.currentItem()
        if not it:
            return
        name, pids = it.data(Qt.ItemDataRole.UserRole)
        ok = QMessageBox.question(self, "Cerrar programa",
                                  f"¿Cerrar {name}?\nPerderás los cambios sin guardar de ese programa.")
        if ok == QMessageBox.StandardButton.Yes:
            n = sm.close_processes(name, pids)
            self.notify(f"Se pidió cerrar {name} ({n} procesos)." if n else f"No se puede cerrar {name}.")
            QTimer.singleShot(1500, self._load_procs)

    def _high(self) -> None:
        self._prev_plan = sm.active_power_plan()
        if sm.set_power_plan(sm.HIGH_PERF):
            self.plan_msg.setText("Plan «Alto rendimiento» activado.")
        else:
            self.plan_msg.setText("No se pudo activar. En algunos equipos (portátiles modernos) ese plan está "
                                  "oculto: cámbialo desde Configuración de Windows → Energía.")

    def _restore(self) -> None:
        plan = self._prev_plan or sm.BALANCED
        self.plan_msg.setText("Plan anterior restaurado." if sm.set_power_plan(plan) else "No se pudo restaurar.")
