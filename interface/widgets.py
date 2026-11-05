"""Widgets reutilizables: tarjetas de juego, gráficas, logo, tarjetas de estadísticas."""
import math
import os
from typing import Callable, List, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QFontMetrics, QIcon, QLinearGradient, QPainter,
                           QPainterPath, QPen, QPixmap)
from PySide6.QtWidgets import (QFrame, QGraphicsDropShadowEffect, QLabel, QLayout, QVBoxLayout, QWidget)

from utils.helpers import color_from_text
from . import theme

PLATFORM_COLORS = {
    "steam": "#1b9ad6", "xbox": "#107c10", "epic": "#9aa0b4", "ubisoft": "#0b84ff", "ea": "#ff4747", "gog": "#a855f7",
    "battlenet": "#00aeff", "rockstar": "#fcaf17", "other": "#6b6b90",
}
PLATFORM_LABELS = {
    "steam": "Steam", "xbox": "Xbox", "epic": "Epic", "ubisoft": "Ubisoft", "ea": "EA", "gog": "GOG",
    "battlenet": "Battle.net", "rockstar": "Rockstar", "other": "Otro",
}
DPR = 2  # las tarjetas se dibujan a doble resolución para que se vean nítidas


# --------------------------------------------------------------------- utilidades
def clear_layout(layout: QLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w is not None:
            w.deleteLater()
        elif item.layout() is not None:
            clear_layout(item.layout())


def label(text: str = "", name: str = "", wrap: bool = False) -> QLabel:
    lb = QLabel(text)
    if name:
        lb.setObjectName(name)
    lb.setWordWrap(wrap)
    return lb


def h1(text: str) -> QLabel:
    return label(text, "H1")


def h2(text: str) -> QLabel:
    return label(text, "H2")


def muted(text: str, wrap: bool = True) -> QLabel:
    return label(text, "Muted", wrap)


def primary(btn):
    btn.setProperty("primary", True)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    return btn


def card_frame() -> QFrame:
    f = QFrame()
    f.setObjectName("Card")
    return f


def glow(widget: QWidget, color: Optional[str] = None, alpha: int = 70) -> None:
    eff = QGraphicsDropShadowEffect(widget)
    c = QColor(color or theme.current()["accent"])
    c.setAlpha(alpha)
    eff.setColor(c)
    eff.setBlurRadius(28)
    eff.setOffset(0, 0)
    widget.setGraphicsEffect(eff)


def app_icon() -> QIcon:
    pm = QPixmap(256, 256)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    g = QLinearGradient(0, 0, 256, 256)
    g.setColorAt(0, QColor("#8b5cf6"))
    g.setColorAt(1, QColor("#38bdf8"))
    path = QPainterPath()
    path.addRoundedRect(QRectF(16, 16, 224, 224), 56, 56)
    p.fillPath(path, QBrush(g))
    p.setPen(QColor("#07070d"))
    f = QFont("Segoe UI", 120)
    f.setBold(True)
    p.setFont(f)
    p.drawText(QRectF(0, 0, 256, 256), Qt.AlignmentFlag.AlignCenter, "G")
    p.end()
    return QIcon(pm)


# ----------------------------------------------------------------------- logo
class LogoWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(64)

    def paintEvent(self, _):
        t = theme.current()
        p = QPainter(self)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        f = QFont("Segoe UI", 17)
        f.setBold(True)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2.5)
        p.setFont(f)
        g = QLinearGradient(0, 0, self.width(), 0)
        g.setColorAt(0, QColor(t["accent"]))
        g.setColorAt(1, QColor(t["accent2"]))
        p.setPen(QPen(QBrush(g), 1))
        p.drawText(QRectF(20, 0, self.width() - 20, 64), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                   "GAMESWORD")


# ----------------------------------------------------------------- stat card
class StatCard(QFrame):
    def __init__(self, title: str, value: str = "—", sub: str = ""):
        super().__init__()
        self.setObjectName("Card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(2)
        self.title = muted(title, wrap=False)
        self.value = label(value, "Value")
        self.sub = muted(sub, wrap=False)
        lay.addWidget(self.title)
        lay.addWidget(self.value)
        lay.addWidget(self.sub)
        glow(self, alpha=45)

    def set(self, value: str, sub: str = "") -> None:
        self.value.setText(value)
        self.sub.setText(sub)


# --------------------------------------------------------- tarjeta de portada
def _wrap_two_lines(text: str, fm: QFontMetrics, width: int) -> List[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if fm.horizontalAdvance(trial) <= width:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
        if len(lines) == 2:
            break
    if cur and len(lines) < 2:
        lines.append(cur)
    if len(lines) == 2 and " ".join(lines) != text:
        lines[1] = fm.elidedText(lines[1] + "…", Qt.TextElideMode.ElideRight, width)
    return [fm.elidedText(l, Qt.TextElideMode.ElideRight, width) for l in lines] or [""]


def make_card_pixmap(title: str, platform: str = "other", cover_path: str = "", w: int = 200, h: int = 280,
                     subtitle: str = "", favorite: bool = False, playing: bool = False,
                     installed: bool = True) -> QPixmap:
    t = theme.current()
    pm = QPixmap(w * DPR, h * DPR)
    pm.setDevicePixelRatio(DPR)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform |
                     QPainter.RenderHint.TextAntialiasing)
    clip = QPainterPath()
    clip.addRoundedRect(QRectF(0, 0, w, h), 14, 14)
    p.setClipPath(clip)

    cover = QPixmap(cover_path) if cover_path and os.path.exists(cover_path) else QPixmap()
    if not cover.isNull():
        scaled = cover.scaled(w * DPR, h * DPR, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                              Qt.TransformationMode.SmoothTransformation)
        scaled.setDevicePixelRatio(DPR)
        x = (scaled.width() / DPR - w) / 2
        y = (scaled.height() / DPR - h) / 2
        p.drawPixmap(QPointF(-x, -y), scaled)
    else:
        hue, s, v = color_from_text(title)
        g = QLinearGradient(0, 0, w, h)
        g.setColorAt(0, QColor.fromHsv(hue, s, v))
        g.setColorAt(1, QColor.fromHsv((hue + 55) % 360, s, max(v - 70, 40)))
        p.fillRect(QRectF(0, 0, w, h), QBrush(g))
        initials = "".join(wd[0] for wd in title.split()[:2]).upper() or "?"
        f = QFont("Segoe UI", int(h * 0.2))
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(255, 255, 255, 75))
        p.drawText(QRectF(0, 0, w, h * 0.68), Qt.AlignmentFlag.AlignCenter, initials)

    if not installed:                                   # juego de tu cuenta sin instalar: apagado
        p.fillRect(QRectF(0, 0, w, h), QColor(8, 8, 16, 150))
    shade = QLinearGradient(0, h * 0.5, 0, h)
    shade.setColorAt(0, QColor(0, 0, 0, 0))
    shade.setColorAt(1, QColor(5, 5, 12, 235))
    p.fillRect(QRectF(0, 0, w, h), QBrush(shade))

    tf = QFont("Segoe UI", 10)
    tf.setBold(True)
    p.setFont(tf)
    fm = QFontMetrics(tf)
    lines = _wrap_two_lines(title, fm, w - 24)
    base = h - (30 if subtitle else 14) - 18 * len(lines)
    p.setPen(QColor("#ffffff"))
    for i, line in enumerate(lines):
        p.drawText(QPointF(12, base + 14 + 18 * i), line)
    if subtitle:
        sf = QFont("Segoe UI", 9)
        p.setFont(sf)
        p.setPen(QColor(215, 215, 240, 200))
        p.drawText(QPointF(12, h - 12), subtitle)

    # insignia de plataforma
    label_txt = PLATFORM_LABELS.get(platform, platform.title())
    bf = QFont("Segoe UI", 8)
    bf.setBold(True)
    p.setFont(bf)
    bw = QFontMetrics(bf).horizontalAdvance(label_txt) + 16
    badge = QRectF(10, 10, bw, 20)
    p.setPen(Qt.PenStyle.NoPen)
    col = QColor(PLATFORM_COLORS.get(platform, PLATFORM_COLORS["other"]))
    col.setAlpha(225)
    p.setBrush(col)
    p.drawRoundedRect(badge, 10, 10)
    p.setPen(QColor("#ffffff"))
    p.drawText(badge, Qt.AlignmentFlag.AlignCenter, label_txt)

    if favorite:
        p.setPen(QColor("#fbbf24"))
        sf2 = QFont("Segoe UI", 14)
        p.setFont(sf2)
        p.drawText(QRectF(w - 34, 6, 28, 28), Qt.AlignmentFlag.AlignCenter, "★")

    if playing:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(t["success"]))
        p.drawRoundedRect(QRectF(10, 36, 78, 18), 9, 9)
        p.setPen(QColor("#04130c"))
        pf = QFont("Segoe UI", 8)
        pf.setBold(True)
        p.setFont(pf)
        p.drawText(QRectF(10, 36, 78, 18), Qt.AlignmentFlag.AlignCenter, "● JUGANDO")

    if not installed:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(30, 30, 52, 235))
        p.drawRoundedRect(QRectF(10, 36, 100, 18), 9, 9)
        p.setPen(QColor("#c9c9ee"))
        nf = QFont("Segoe UI", 8)
        nf.setBold(True)
        p.setFont(nf)
        p.drawText(QRectF(10, 36, 100, 18), Qt.AlignmentFlag.AlignCenter, "⬇ NO INSTALADO")

    p.setClipping(False)
    p.setPen(QPen(QColor(255, 255, 255, 38), 1))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 14, 14)
    p.end()
    return pm


# -------------------------------------------------------------------- gráficas
class BarChart(QWidget):
    """Barras verticales con degradado neón."""

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(230)
        self.items: List[Tuple[str, float]] = []
        self.fmt: Callable[[float], str] = lambda v: f"{v:.1f}"

    def set_data(self, items: List[Tuple[str, float]], fmt: Optional[Callable] = None) -> None:
        self.items = items
        if fmt:
            self.fmt = fmt
        self.update()

    def paintEvent(self, _):
        t = theme.current()
        p = QPainter(self)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        w, h = self.width(), self.height()
        peak = max((v for _, v in self.items), default=0)
        if not self.items or peak <= 0:
            p.setPen(QColor(t["muted"]))
            p.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, "Sin datos todavía — ¡a jugar!")
            return
        left, right, top, bottom = 8, 8, 26, 30
        plot_h = h - top - bottom
        p.setPen(QPen(QColor(t["border"]), 1, Qt.PenStyle.DotLine))
        for i in range(5):
            y = top + plot_h * i / 4
            p.drawLine(QPointF(left, y), QPointF(w - right, y))
        n = len(self.items)
        slot = (w - left - right) / n
        bar_w = min(slot * 0.62, 46)
        step = max(1, math.ceil(n / max(1, (w - left - right) / 54)))
        small = QFont("Segoe UI", 8)
        p.setFont(small)
        for i, (lab, val) in enumerate(self.items):
            x = left + slot * i + (slot - bar_w) / 2
            bh = plot_h * val / peak
            if val > 0:
                rect = QRectF(x, top + plot_h - bh, bar_w, max(bh, 3))
                g = QLinearGradient(rect.topLeft(), rect.bottomLeft())
                g.setColorAt(0, QColor(t["accent2"]))
                g.setColorAt(1, QColor(t["accent"]))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(g))
                p.drawRoundedRect(rect, 6, 6)
                if n <= 16 or i % step == 0:
                    p.setPen(QColor(t["text"]))
                    p.drawText(QRectF(x - 14, rect.top() - 18, bar_w + 28, 16), Qt.AlignmentFlag.AlignCenter,
                               self.fmt(val))
            if i % step == 0:
                p.setPen(QColor(t["muted"]))
                p.drawText(QRectF(left + slot * i - 4, h - bottom + 6, slot + 8, 18), Qt.AlignmentFlag.AlignCenter, lab)


class HBarChart(QWidget):
    """Barras horizontales (ranking)."""

    def __init__(self):
        super().__init__()
        self.items: List[Tuple[str, float]] = []
        self.fmt: Callable[[float], str] = lambda v: f"{v:.1f}"
        self.setMinimumHeight(60)

    def set_data(self, items: List[Tuple[str, float]], fmt: Optional[Callable] = None) -> None:
        self.items = items
        if fmt:
            self.fmt = fmt
        self.setMinimumHeight(max(60, 38 * len(items) + 8))
        self.update()

    def paintEvent(self, _):
        t = theme.current()
        p = QPainter(self)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        w = self.width()
        peak = max((v for _, v in self.items), default=0)
        if not self.items or peak <= 0:
            p.setPen(QColor(t["muted"]))
            p.drawText(QRectF(0, 0, w, self.height()), Qt.AlignmentFlag.AlignCenter, "Sin datos todavía")
            return
        label_w, value_w, row_h = 170, 70, 38
        fm = QFontMetrics(self.font())
        for i, (lab, val) in enumerate(self.items):
            y = 4 + i * row_h
            p.setPen(QColor(t["text"]))
            p.drawText(QRectF(0, y, label_w - 10, row_h), Qt.AlignmentFlag.AlignVCenter,
                       fm.elidedText(lab, Qt.TextElideMode.ElideRight, label_w - 12))
            track = QRectF(label_w, y + 10, w - label_w - value_w, 16)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(t["panel"]))
            p.drawRoundedRect(track, 8, 8)
            bar = QRectF(track.left(), track.top(), max(track.width() * val / peak, 10), track.height())
            g = QLinearGradient(bar.topLeft(), bar.topRight())
            g.setColorAt(0, QColor(t["accent"]))
            g.setColorAt(1, QColor(t["accent2"]))
            p.setBrush(QBrush(g))
            p.drawRoundedRect(bar, 8, 8)
            p.setPen(QColor(t["muted"]))
            p.drawText(QRectF(w - value_w + 8, y, value_w - 8, row_h), Qt.AlignmentFlag.AlignVCenter, self.fmt(val))


# ------------------------------------------------------------------ vista base
class BaseView(QWidget):
    message = Signal(str)

    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx

    def refresh(self) -> None:  # lo sobreescriben las vistas
        pass

    def notify(self, text: str) -> None:
        self.message.emit(text)


class GaugeBar(QWidget):
    """Barra de porcentaje con degradado; cambia a rojo cuando el uso es muy alto."""

    def __init__(self, title: str):
        super().__init__()
        self.title, self.value, self.text = title, 0.0, "—"
        self.setFixedHeight(54)

    def set_value(self, percent: float, text: str) -> None:
        self.value, self.text = max(0.0, min(100.0, percent)), text
        self.update()

    def paintEvent(self, _):
        t = theme.current()
        p = QPainter(self)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        w = self.width()
        p.setPen(QColor(t["muted"]))
        p.drawText(QRectF(0, 0, w, 20), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.title)
        p.setPen(QColor(t["text"]))
        p.drawText(QRectF(0, 0, w, 20), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, self.text)
        track = QRectF(0, 28, w, 14)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(t["panel"]))
        p.drawRoundedRect(track, 7, 7)
        bar = QRectF(0, 28, max(w * self.value / 100, 8 if self.value > 0 else 0), 14)
        g = QLinearGradient(bar.topLeft(), bar.topRight())
        if self.value >= 90:
            g.setColorAt(0, QColor(t["warn"]))
            g.setColorAt(1, QColor(t["danger"]))
        else:
            g.setColorAt(0, QColor(t["accent"]))
            g.setColorAt(1, QColor(t["accent2"]))
        p.setBrush(QBrush(g))
        p.drawRoundedRect(bar, 7, 7)


def make_avatar(name: str, path: str = "", size: int = 96) -> QPixmap:
    """Avatar circular: la imagen elegida, o iniciales sobre un degradado generado a partir del nombre."""
    t = theme.current()
    pm = QPixmap(size * DPR, size * DPR)
    pm.setDevicePixelRatio(DPR)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform |
                     QPainter.RenderHint.TextAntialiasing)
    clip = QPainterPath()
    clip.addEllipse(QRectF(2, 2, size - 4, size - 4))
    p.setClipPath(clip)
    img = QPixmap(path) if path and os.path.exists(path) else QPixmap()
    if not img.isNull():
        scaled = img.scaled(size * DPR, size * DPR, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                            Qt.TransformationMode.SmoothTransformation)
        scaled.setDevicePixelRatio(DPR)
        p.drawPixmap(QPointF(-(scaled.width() / DPR - size) / 2, -(scaled.height() / DPR - size) / 2), scaled)
    else:
        hue, s, v = color_from_text(name or "?")
        g = QLinearGradient(0, 0, size, size)
        g.setColorAt(0, QColor(t["accent"]))
        g.setColorAt(1, QColor.fromHsv(hue, s, max(v, 140)))
        p.fillRect(QRectF(0, 0, size, size), QBrush(g))
        f = QFont("Segoe UI", int(size * 0.34))
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor("#ffffff"))
        p.drawText(QRectF(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, (name or "?")[:2].upper())
    p.setClipping(False)
    p.setPen(QPen(QColor(t["accent2"]), 2))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(QRectF(2, 2, size - 4, size - 4))
    p.end()
    return pm
