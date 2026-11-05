"""Tema visual futurista: negro profundo con acentos morado y azul neón."""
from PySide6.QtGui import QColor, QPalette

THEMES = {
    "neon_purple": dict(name="Neón Morado", bg="#07070d", panel="#0d0d18", card="#13132a", hover="#1a1a38",
                        border="#26264a", accent="#8b5cf6", accent2="#38bdf8", text="#f1f1ff", muted="#8b8bb0",
                        success="#34d399", danger="#f43f5e", warn="#fbbf24"),
    "ice_blue": dict(name="Azul Hielo", bg="#05090f", panel="#0a111c", card="#101b2c", hover="#162640",
                     border="#1f3350", accent="#3b82f6", accent2="#22d3ee", text="#eef6ff", muted="#7f98b8",
                     success="#34d399", danger="#f43f5e", warn="#fbbf24"),
    "cyber_magenta": dict(name="Cyber Magenta", bg="#0a060c", panel="#130b17", card="#1d1124", hover="#2a1735",
                          border="#43224f", accent="#d946ef", accent2="#8b5cf6", text="#fdf1ff", muted="#b08cb8",
                          success="#34d399", danger="#fb7185", warn="#fbbf24"),
}

CURRENT: dict = {}


def _soft(hex_color: str, alpha: float) -> str:
    c = QColor(hex_color)
    return f"rgba({c.red()},{c.green()},{c.blue()},{int(alpha * 255)})"


TEMPLATE = """
* { font-family: "Segoe UI", "Inter", "Helvetica Neue", sans-serif; font-size: 14px; color: @text; }
QMainWindow, QDialog, QMessageBox, QFileDialog { background: @bg; }
QWidget#Root { background: @bg; }
QLabel { background: transparent; }
QToolTip { background: @card; color: @text; border: 1px solid @accent; padding: 6px 8px; }

QFrame#Card { background: @card; border: 1px solid @border; border-radius: 14px; }
QFrame#Sidebar { background: @panel; border: none; border-right: 1px solid @border; }
QFrame#BubbleUser { background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 @accent, stop:1 @accent2); border-radius: 16px; }
QFrame#BubbleUser QLabel { color: white; }
QFrame#BubbleAI { background: @card; border: 1px solid @border; border-radius: 16px; }
QFrame#Badge { background: @panel; border: 1px solid @border; border-radius: 12px; }
QFrame#BadgeOn { background: @accent_soft; border: 1px solid @accent; border-radius: 12px; }

QLabel#H1 { font-size: 26px; font-weight: 700; }
QLabel#H2 { font-size: 17px; font-weight: 600; }
QLabel#Value { font-size: 28px; font-weight: 700; }
QLabel#Muted { color: @muted; }
QLabel#Success { color: @success; }
QLabel#Danger { color: @danger; }

QPushButton { background: @card; border: 1px solid @border; border-radius: 9px; padding: 8px 16px; }
QPushButton:hover { border-color: @accent; background: @hover; }
QPushButton:pressed { background: @accent_soft; }
QPushButton:disabled { color: @muted; border-color: @border; background: @panel; }
QPushButton[primary="true"] { border: none; color: white; font-weight: 600;
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 @accent, stop:1 @accent2); }
QPushButton[primary="true"]:hover { border: 1px solid rgba(255,255,255,140); }
QPushButton[primary="true"]:disabled { background: @border; color: @muted; }
QPushButton[ghost="true"] { background: transparent; border: none; color: @muted; padding: 6px 10px; }
QPushButton[ghost="true"]:hover { color: @text; background: @hover; }
QPushButton[chip="true"] { border-radius: 15px; padding: 6px 14px; background: @panel; }
QPushButton[chip="true"]:checked { background: @accent_soft; border: 1px solid @accent; }
QPushButton[danger="true"]:hover { border-color: @danger; color: @danger; }
QPushButton#NavButton { text-align: left; padding: 13px 20px; border: none; border-left: 3px solid transparent;
    border-radius: 0; background: transparent; color: @muted; font-size: 15px; }
QPushButton#NavButton:hover { background: @hover; color: @text; }
QPushButton#NavButton:checked { background: @accent_soft; border-left: 3px solid @accent; color: @text; font-weight: 600; }

QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background: @panel; border: 1px solid @border; border-radius: 9px; padding: 8px 12px;
    selection-background-color: @accent; selection-color: white; }
QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus { border: 1px solid @accent; }
QLineEdit:disabled { color: @muted; }
QComboBox QAbstractItemView { background: @card; border: 1px solid @border; outline: 0;
    selection-background-color: @accent_soft; selection-color: @text; padding: 4px; }

QListWidget { background: transparent; border: none; outline: 0; }
QListWidget#Grid::item { border-radius: 14px; padding: 4px; margin: 2px; }
QListWidget#Grid::item:hover { background: @hover; }
QListWidget#Grid::item:selected { background: @accent_soft; border: 1px solid @accent; }
QListWidget#List { background: @panel; border: 1px solid @border; border-radius: 12px; padding: 6px; }
QListWidget#List::item { padding: 10px 12px; border-radius: 8px; }
QListWidget#List::item:hover { background: @hover; }
QListWidget#List::item:selected { background: @accent_soft; color: @text; }

QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: @border; border-radius: 4px; min-height: 36px; }
QScrollBar::handle:vertical:hover { background: @accent; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal { background: @border; border-radius: 4px; min-width: 36px; }
QScrollBar::handle:horizontal:hover { background: @accent; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: none; }

QCheckBox { spacing: 10px; background: transparent; }
QCheckBox::indicator { width: 18px; height: 18px; border-radius: 5px; border: 1px solid @border; background: @panel; }
QCheckBox::indicator:hover { border-color: @accent; }
QCheckBox::indicator:checked { background: @accent; border-color: @accent; }

QSlider::groove:horizontal { height: 6px; background: @border; border-radius: 3px; }
QSlider::sub-page:horizontal { background: @accent; border-radius: 3px; }
QSlider::handle:horizontal { background: white; width: 16px; margin: -5px 0; border-radius: 8px; }

QMenu { background: @card; border: 1px solid @border; padding: 6px; border-radius: 8px; }
QMenu::item { padding: 8px 26px; border-radius: 6px; }
QMenu::item:selected { background: @accent_soft; }
QMenu::separator { height: 1px; background: @border; margin: 6px 8px; }

QStatusBar { background: @panel; border-top: 1px solid @border; color: @muted; }
QStatusBar QLabel { color: @muted; }
"""


COMPACT_SWAPS = [("font-size: 14px", "font-size: 12px"), ("padding: 8px 16px", "padding: 5px 12px"),
                 ("padding: 13px 20px", "padding: 8px 16px"), ("padding: 8px 12px", "padding: 5px 9px"),
                 ("font-size: 26px", "font-size: 21px"), ("font-size: 28px", "font-size: 22px"),
                 ("font-size: 15px", "font-size: 13px"), ("font-size: 17px", "font-size: 15px")]


def build_stylesheet(t: dict, compact: bool = False) -> str:
    tokens = dict(t)
    tokens["accent_soft"] = _soft(t["accent"], 0.18)
    qss = TEMPLATE
    for key in sorted(tokens, key=len, reverse=True):
        if key != "name":
            qss = qss.replace("@" + key, tokens[key])
    if compact:
        for old, new in COMPACT_SWAPS:
            qss = qss.replace(old, new)
    return qss


def _valid_hex(value: str) -> bool:
    return isinstance(value, str) and len(value) == 7 and value.startswith("#") and \
        all(c in "0123456789abcdefABCDEF" for c in value[1:])


def apply_theme(app, key: str, accent: str = "", accent2: str = "", compact: bool = False) -> dict:
    t = dict(THEMES.get(key, THEMES["neon_purple"]))
    if _valid_hex(accent):
        t["accent"] = accent
    if _valid_hex(accent2):
        t["accent2"] = accent2
    CURRENT.clear()
    CURRENT.update(t)
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(t["bg"]))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(t["text"]))
    pal.setColor(QPalette.ColorRole.Base, QColor(t["panel"]))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(t["card"]))
    pal.setColor(QPalette.ColorRole.Text, QColor(t["text"]))
    pal.setColor(QPalette.ColorRole.Button, QColor(t["card"]))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(t["text"]))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(t["accent"]))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(t["card"]))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor(t["text"]))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(t["muted"]))
    app.setPalette(pal)
    app.setStyleSheet(build_stylesheet(t, compact))
    return t


def apply_from_settings(app, settings) -> dict:
    return apply_theme(app, settings.get("app.theme", "neon_purple"), settings.get("app.accent", ""),
                       settings.get("app.accent2", ""), bool(settings.get("app.compact", False)))


def current() -> dict:
    if not CURRENT:
        CURRENT.update(THEMES["neon_purple"])
    return CURRENT
