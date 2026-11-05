"""Diálogos: añadir / editar juego."""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout, QLineEdit, QListWidget,
                               QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout, QWidget)

from core.models import Game
from .widgets import PLATFORM_LABELS, h2, muted, primary

EXE_FILTER = "Ejecutables (*.exe *.bat *.lnk);;Todos los archivos (*)"
IMG_FILTER = "Imágenes (*.png *.jpg *.jpeg *.webp);;Todos los archivos (*)"


class GameDialog(QDialog):
    def __init__(self, parent=None, game: Game = None):
        super().__init__(parent)
        self.editing = game is not None
        self._game = game or Game()
        self.setWindowTitle("Editar juego" if self.editing else "Añadir juego")
        self.setMinimumWidth(560)

        self.name = QLineEdit(self._game.name)
        self.platform = QComboBox()
        for key, lab in PLATFORM_LABELS.items():
            self.platform.addItem(lab, key)
        idx = self.platform.findData(self._game.platform)
        self.platform.setCurrentIndex(max(idx, 0))
        self.exe = QLineEdit(self._game.exe_path)
        self.exe.setPlaceholderText(r"C:\Juegos\MiJuego\juego.exe")
        self.uri = QLineEdit(self._game.launch_uri)
        self.uri.setPlaceholderText("steam://rungameid/12345  ·  com.epicgames.launcher://apps/…")
        self.install = QLineEdit(self._game.install_dir)
        self.install.setPlaceholderText("Carpeta del juego (para medir las horas jugadas)")
        self.process = QLineEdit(self._game.process_name)
        self.process.setPlaceholderText("juego.exe (opcional, para medir las horas)")
        self.cover = QLineEdit(self._game.cover_path)
        self.cover.setPlaceholderText("Imagen de portada (opcional)")
        self.tags = QLineEdit(self._game.tags)
        self.tags.setPlaceholderText("accion, cooperativo, mundo abierto")

        form = QFormLayout()
        form.setSpacing(10)
        form.addRow("Nombre *", self.name)
        form.addRow("Plataforma", self.platform)
        form.addRow("Ejecutable", self._with_browse(self.exe, self._pick_exe))
        form.addRow("URI de inicio", self.uri)
        form.addRow("Carpeta", self._with_browse(self.install, self._pick_dir))
        form.addRow("Proceso", self.process)
        form.addRow("Portada", self._with_browse(self.cover, self._pick_cover))
        form.addRow("Etiquetas", self.tags)

        ok = primary(QPushButton("Guardar"))
        cancel = QPushButton("Cancelar")
        ok.clicked.connect(self._accept)
        cancel.clicked.connect(self.reject)
        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(cancel)
        buttons.addWidget(ok)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 22)
        lay.setSpacing(12)
        lay.addWidget(h2(self.windowTitle()))
        lay.addWidget(muted("Indica un ejecutable o un URI de la plataforma. La carpeta/proceso permiten "
                            "contar el tiempo jugado."))
        lay.addLayout(form)
        lay.addLayout(buttons)

    @staticmethod
    def _with_browse(edit: QLineEdit, slot) -> QWidget:
        w = QWidget()
        row = QHBoxLayout(w)
        row.setContentsMargins(0, 0, 0, 0)
        btn = QPushButton("…")
        btn.setFixedWidth(42)
        btn.clicked.connect(slot)
        row.addWidget(edit)
        row.addWidget(btn)
        return w

    def _pick_exe(self):
        path, _ = QFileDialog.getOpenFileName(self, "Elegir ejecutable", "", EXE_FILTER)
        if not path:
            return
        p = Path(path)
        self.exe.setText(str(p))
        if not self.name.text().strip():
            self.name.setText(p.stem)
        if not self.install.text().strip():
            self.install.setText(str(p.parent))
        if not self.process.text().strip():
            self.process.setText(p.name)

    def _pick_dir(self):
        path = QFileDialog.getExistingDirectory(self, "Carpeta del juego")
        if path:
            self.install.setText(path)

    def _pick_cover(self):
        path, _ = QFileDialog.getOpenFileName(self, "Elegir portada", "", IMG_FILTER)
        if path:
            self.cover.setText(path)

    def _accept(self):
        if not self.name.text().strip():
            QMessageBox.warning(self, "Falta el nombre", "Escribe el nombre del juego.")
            return
        if not self.exe.text().strip() and not self.uri.text().strip():
            QMessageBox.warning(self, "Falta cómo iniciarlo", "Indica un ejecutable o un URI de inicio.")
            return
        self.accept()

    def result_game(self) -> Game:
        g = self._game
        g.name = self.name.text().strip()
        g.platform = self.platform.currentData()
        g.exe_path = self.exe.text().strip().strip('"')
        g.launch_uri = self.uri.text().strip()
        g.install_dir = self.install.text().strip().strip('"')
        g.process_name = self.process.text().strip()
        g.cover_path = self.cover.text().strip().strip('"')
        g.tags = ", ".join(t.strip() for t in self.tags.text().split(",") if t.strip())
        return g


class MemoryDialog(QDialog):
    """Ver y borrar lo que Gamesword AI recuerda."""

    def __init__(self, parent, db):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Memoria de Gamesword AI")
        self.setMinimumSize(520, 420)
        self.list = QListWidget()
        self.list.setObjectName("List")
        del_one, del_all, close = QPushButton("Borrar la seleccionada"), QPushButton("Borrar toda la memoria"), \
            primary(QPushButton("Cerrar"))
        del_one.clicked.connect(self._delete_one)
        del_all.clicked.connect(self._delete_all)
        close.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addWidget(del_one)
        row.addWidget(del_all)
        row.addStretch()
        row.addWidget(close)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 22)
        lay.setSpacing(12)
        lay.addWidget(h2("Memoria de Gamesword AI"))
        lay.addWidget(muted("Lo que le pides que recuerde («recuerda que…»). Solo se guarda en tu PC y se envía al "
                            "modelo de IA como contexto si tienes uno configurado.", wrap=True))
        lay.addWidget(self.list, 1)
        lay.addLayout(row)
        self._load()

    def _load(self) -> None:
        self.list.clear()
        items = self.db.list_memory()
        if not items:
            self.list.addItem("La memoria está vacía.")
        for m in items:
            it = QListWidgetItem(m["text"])
            it.setData(Qt.ItemDataRole.UserRole, m["id"])
            self.list.addItem(it)

    def _delete_one(self) -> None:
        it = self.list.currentItem()
        mid = it.data(Qt.ItemDataRole.UserRole) if it else None
        if mid:
            self.db.delete_memory(mid)
            self._load()

    def _delete_all(self) -> None:
        if self.db.list_memory() and QMessageBox.question(
                self, "Borrar memoria", "¿Borrar TODA la memoria de Gamesword AI?") == QMessageBox.StandardButton.Yes:
            self.db.delete_memory()
            self._load()


class CustomCommandsDialog(QDialog):
    """Frases propias que abren juegos o programas en orden, p. ej. «modo noche» → Discord, Rocket League."""

    def __init__(self, parent, settings):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Comandos personalizados")
        self.setMinimumSize(560, 460)
        self.items = [dict(c) for c in (settings.get("ai.custom_commands", []) or [])]
        self.list = QListWidget()
        self.list.setObjectName("List")
        self.phrase = QLineEdit()
        self.phrase.setPlaceholderText("Frase, p. ej.: modo noche")
        self.targets = QLineEdit()
        self.targets.setPlaceholderText("Qué abrir, separado por comas y en orden: Discord, Rocket League")
        add, remove = primary(QPushButton("Añadir comando")), QPushButton("Eliminar el seleccionado")
        save, cancel = primary(QPushButton("Guardar")), QPushButton("Cancelar")
        add.clicked.connect(self._add)
        remove.clicked.connect(self._remove)
        save.clicked.connect(self._save)
        cancel.clicked.connect(self.reject)
        row = QHBoxLayout()
        row.addWidget(add)
        row.addWidget(remove)
        row.addStretch()
        row2 = QHBoxLayout()
        row2.addStretch()
        row2.addWidget(cancel)
        row2.addWidget(save)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 22)
        lay.setSpacing(10)
        lay.addWidget(h2("Comandos personalizados"))
        lay.addWidget(muted("Al decir o escribir la frase (también con otras palabras alrededor), Gamesword AI abre "
                            "esos juegos o programas en ese orden.", wrap=True))
        lay.addWidget(self.list, 1)
        lay.addWidget(self.phrase)
        lay.addWidget(self.targets)
        lay.addLayout(row)
        lay.addLayout(row2)
        self._reload()

    def _reload(self) -> None:
        self.list.clear()
        for c in self.items:
            self.list.addItem(f"«{c['phrase']}»  →  {', '.join(c['targets'])}")

    def _add(self) -> None:
        phrase = self.phrase.text().strip()
        targets = [t.strip() for t in self.targets.text().split(",") if t.strip()]
        if len(phrase) < 3 or not targets:
            QMessageBox.warning(self, "Comando", "Escribe una frase (mínimo 3 letras) y al menos un juego o programa.")
            return
        self.items = [c for c in self.items if c["phrase"].lower() != phrase.lower()]
        self.items.append({"phrase": phrase, "targets": targets})
        self.phrase.clear()
        self.targets.clear()
        self._reload()

    def _remove(self) -> None:
        row = self.list.currentRow()
        if 0 <= row < len(self.items):
            del self.items[row]
            self._reload()

    def _save(self) -> None:
        self.settings.set("ai.custom_commands", self.items)
        self.accept()
