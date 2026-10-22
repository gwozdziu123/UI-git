"""Design system (tokeny el_Fuszka) przeniesiony do Qt: kolory, typografia, QSS, ikony."""
from __future__ import annotations

import sys
import weakref
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPalette

from . import icons

# ------------------------------------------------------------------ tokeny
_LIGHT = {
    "bg": "#f2f4f8", "card": "#ffffff", "text": "#111827", "muted": "#6b7280", "line": "#e5e7eb",
    "primary": "#1d4ed8", "primary-weak": "#e6edff", "on-primary": "#ffffff",
    "danger": "#dc2626", "danger-weak": "#fdecec", "on-danger": "#ffffff",
    "warn": "#a16207", "warn-weak": "#fff6e0",
    "card-edge": "#e9ebef", "card-edge-low": "#dde0e6",          # zamiennik cienia `shadow`
    "ok-weak": "#e8f6ed", "ok-text": "#15803d",                  # tło/tekst dodanych linii w podglądzie
}
_DARK = {
    "bg": "#0e1116", "card": "#181c24", "text": "#e8eaf0", "muted": "#9aa2b1", "line": "#2a303c",
    "primary": "#6b93f5", "primary-weak": "#1c2740", "on-primary": "#0b1020",
    "danger": "#f87171", "danger-weak": "#3a1d1d", "on-danger": "#ffffff",
    "warn": "#facc15", "warn-weak": "#3a2f12",
    "card-edge": "#181c24", "card-edge-low": "#181c24",          # w ciemnym motywie bez cienia
    "ok-weak": "#15301f", "ok-text": "#6fdc8c",
}
_SHARED = {
    "s-wycena": "#64748b", "s-w_trakcie": "#d97706", "s-zakonczony": "#16a34a", "s-rozliczony": "#7c3aed",
    "on-status": "#ffffff", "brand-bolt": "#ffc828", "toast-bg": "#111827", "toast-text": "#ffffff",
}

RADIUS = {"xs": 6, "sm": 10, "md": 12, "card": 14, "lg": 18, "sheet": 20}

# Statusy (zawsze ze słowem obok koloru)
STATUS_SYNCED = "s-zakonczony"     # aktualny / bez zmian
STATUS_CHANGES = "s-w_trakcie"     # są niezatwierdzone zmiany
STATUS_OUTGOING = "s-rozliczony"   # commity do wysłania / pobrania
STATUS_NEUTRAL = "s-wycena"        # bez GitHuba, nie repozytorium


class _Theme:
    def __init__(self):
        self.scheme = "light"
        self.colors = {**_LIGHT, **_SHARED}

    def __getitem__(self, key: str) -> str:
        return self.colors[key]

    def q(self, key: str) -> QColor:
        return QColor(self.colors[key])

    @property
    def dark(self) -> bool:
        return self.scheme == "dark"


T = _Theme()

# ------------------------------------------------------------------ typografia
SANS = ["Segoe UI", "-apple-system", ".AppleSystemUIFont", "Roboto", "Noto Sans", "DejaVu Sans"]
MONO = ["Consolas", "Cascadia Mono", "Menlo", "SF Mono", "DejaVu Sans Mono"]


def font(px: int = 16, weight: int = 400, mono: bool = False) -> QFont:
    f = QFont()
    f.setFamilies(MONO if mono else SANS)
    f.setPixelSize(px)
    f.setWeight(QFont.Weight(weight))
    if mono:
        f.setStyleHint(QFont.Monospace)
    return f


# Style tekstu z design systemu: (rozmiar px, waga)
TYPE = {
    "result": (30, 700), "total": (24, 700), "screen-title": (20, 700), "sheet-title": (19, 700),
    "card-title": (17, 700), "input": (16, 400), "body": (16, 400), "body-strong": (16, 600),
    "secondary": (14, 400), "label": (14, 600), "caption": (13, 400), "tab": (12, 600), "section": (14, 700),
}


def tfont(style: str) -> QFont:
    px, w = TYPE[style]
    return font(px, w)


# ------------------------------------------------------------------ ikony powiązane z motywem
_bound: list = []


def bind_icon(widget, name: str, token: str = "primary", size: int = 20, setter: str = "setIcon"):
    """Ustawia ikonę i odświeża ją po zmianie motywu."""
    _bound.append((weakref.ref(widget), name, token, size, setter))
    _apply_icon(widget, name, token, size, setter)


def _apply_icon(widget, name, token, size, setter):
    ic = icons.icon(name, T[token], size, disabled_color=T["muted"])
    getattr(widget, setter)(ic)


def _refresh_icons():
    alive = []
    for ref, name, token, size, setter in _bound:
        w = ref()
        if w is None:
            continue
        try:
            _apply_icon(w, name, token, size, setter)
            alive.append((ref, name, token, size, setter))
        except RuntimeError:  # obiekt C++ usunięty
            pass
    _bound[:] = alive


# ------------------------------------------------------------------ QSS
def _assets_dir() -> Path:
    from .config import config_dir
    d = config_dir() / "theme" / T.scheme
    d.mkdir(parents=True, exist_ok=True)
    return d


def _asset(name: str, color: str, size: int = 16) -> str:
    d = _assets_dir()
    fname = f"{name}-{color.strip('#')}"
    for ratio, suffix in ((1.0, ""), (2.0, "@2x")):
        p = d / f"{fname}{suffix}.png"
        if not p.exists():
            icons.pixmap(name, color, size, ratio).toImage().save(str(p))
    return (d / f"{fname}.png").as_posix()


def build_qss() -> str:
    c = T.colors
    check = _asset("check", c["on-primary"], 14)
    chev = _asset("chev-down", c["muted"], 16)
    return f"""
* {{ outline: 0; }}
QWidget {{ color: {c['text']}; font-size: 16px; }}
QMainWindow, QDialog, QWidget#screen {{ background: {c['bg']}; }}
QDialog#sheet {{ background: {c['card']}; }}
QToolTip {{ background: {c['toast-bg']}; color: {c['toast-text']}; border: 0; padding: 6px 10px; border-radius: 8px; font-size: 13px; }}

/* Karta */
QFrame#card {{ background: {c['card']}; border-radius: {RADIUS['card']}px;
  border: 1px solid {c['card-edge']}; border-bottom-color: {c['card-edge-low']}; }}
QDialog#sheet QFrame#card {{ border: 1px solid {c['line']}; }}
QFrame#sep {{ background: {c['line']}; max-height: 1px; min-height: 1px; border: 0; }}

/* Pasek górny */
QWidget#topbar {{ background: {c['bg']}; }}
QLabel#screenTitle {{ font-size: 20px; font-weight: 700; }}
QLabel#cardTitle {{ font-size: 17px; font-weight: 700; }}
QLabel#sheetTitle {{ font-size: 19px; font-weight: 700; }}
QLabel#sectionLabel {{ font-size: 14px; font-weight: 700; color: {c['muted']}; }}
QLabel#fieldLabel {{ font-size: 14px; font-weight: 600; color: {c['muted']}; }}
QLabel#muted, QLabel#secondary {{ color: {c['muted']}; font-size: 14px; }}
QLabel#hint, QLabel#caption {{ color: {c['muted']}; font-size: 13px; }}
QLabel#emptyText {{ color: {c['muted']}; font-size: 16px; }}
QLabel a {{ color: {c['primary']}; }}

/* Przyciski */
QPushButton {{ min-height: 40px; padding: 0 16px; border-radius: {RADIUS['md']}px; font-weight: 700;
  background: transparent; border: 1px solid {c['line']}; color: {c['text']}; }}
QPushButton:pressed {{ background: {c['line']}; }}
QPushButton:disabled {{ color: {c['muted']}; border-color: {c['line']}; background: transparent; }}
QPushButton#primary {{ background: {c['primary']}; border: 1px solid {c['primary']}; color: {c['on-primary']}; }}
QPushButton#primary:pressed {{ background: {QColor(c['primary']).darker(110).name()}; }}
QPushButton#primary:disabled {{ background: {c['line']}; border-color: {c['line']}; color: {c['muted']}; }}
QPushButton#danger {{ background: {c['danger']}; border: 1px solid {c['danger']}; color: {c['on-danger']}; }}
QPushButton#dangerGhost {{ color: {c['danger']}; }}
QPushButton#tall {{ min-height: 48px; }}
QPushButton#add {{ border: 0; color: {c['primary']}; padding: 0 10px; border-radius: {RADIUS['sm']}px; min-height: 36px; }}
QPushButton#add:pressed {{ background: {c['primary-weak']}; }}
QPushButton#add:disabled {{ color: {c['muted']}; }}
QPushButton#iconBtn {{ border: 0; min-width: 40px; max-width: 40px; min-height: 40px; max-height: 40px;
  padding: 0; border-radius: 20px; }}
QPushButton#iconBtn:pressed {{ background: {c['line']}; }}
QPushButton#account {{ border-radius: 20px; font-weight: 600; padding: 0 14px; }}
QPushButton#seg {{ min-height: 36px; border-radius: {RADIUS['sm']}px; font-size: 14px; font-weight: 600; padding: 0 8px;
  background: {c['card']}; }}
QPushButton#seg:checked {{ background: {c['primary']}; border-color: {c['primary']}; color: {c['on-primary']}; }}
QPushButton#link {{ border: 0; padding: 0; min-height: 0; color: {c['primary']}; font-weight: 600; text-align: left; }}

/* Pola */
QLineEdit, QPlainTextEdit#inp, QComboBox {{ background: {c['bg']}; border: 1px solid {c['line']};
  border-radius: {RADIUS['md']}px; padding: 0 12px; min-height: 44px; font-size: 16px;
  selection-background-color: {c['primary']}; selection-color: {c['on-primary']}; }}
QPlainTextEdit#inp {{ padding: 8px 10px; }}
QLineEdit:focus, QPlainTextEdit#inp:focus, QComboBox:focus, QComboBox:on {{ border-color: {c['primary']}; background: {c['card']}; }}
QLineEdit[err="true"] {{ border-color: {c['danger']}; background: {c['danger-weak']}; }}
QLineEdit#search {{ border-radius: 22px; background: {c['card']}; padding-left: 8px; }}
QComboBox::drop-down {{ border: 0; width: 36px; }}
QComboBox::down-arrow {{ image: url({chev}); width: 16px; height: 16px; }}
QComboBox QAbstractItemView {{ background: {c['card']}; border: 1px solid {c['line']}; border-radius: {RADIUS['md']}px;
  padding: 4px; selection-background-color: {c['primary-weak']}; selection-color: {c['text']}; }}

/* Pole wyboru */
QCheckBox {{ spacing: 10px; font-weight: 600; min-height: 32px; }}
QCheckBox::indicator {{ width: 20px; height: 20px; border-radius: 6px; border: 2px solid {c['line']}; background: {c['card']}; }}
QCheckBox::indicator:checked {{ background: {c['primary']}; border-color: {c['primary']}; image: url({check}); }}
QCheckBox::indicator:disabled {{ background: {c['line']}; }}
QCheckBox:disabled {{ color: {c['muted']}; }}

/* Listy i tabele */
QListWidget#plain::item {{ padding: 0 8px; border-radius: 8px; font-size: 15px; }}
QListWidget#plain::item:selected {{ background: {c['primary-weak']}; color: {c['text']}; }}
QListView::indicator {{ width: 18px; height: 18px; border-radius: 5px; border: 2px solid {c['line']}; background: {c['card']}; }}
QListView::indicator:checked {{ background: {c['primary']}; border-color: {c['primary']}; image: url({check}); }}
QListView, QTableView {{ background: transparent; border: 0; }}
QTableView {{ gridline-color: transparent; selection-background-color: {c['primary-weak']}; selection-color: {c['text']}; }}
QTableView::item {{ border-bottom: 1px solid {c['line']}; padding: 0 8px; }}
QTableView::item:selected {{ background: {c['primary-weak']}; color: {c['text']}; }}
QHeaderView::section {{ background: transparent; border: 0; border-bottom: 1px solid {c['line']}; padding: 8px;
  color: {c['muted']}; font-size: 13px; font-weight: 700; }}
QPlainTextEdit {{ background: {c['card']}; border: 0; selection-background-color: {c['primary']}; selection-color: {c['on-primary']}; }}

/* Zakładki – pigułka jak wskaźnik aktywnej zakładki */
QTabWidget::pane {{ border: 0; }}
QTabBar {{ qproperty-drawBase: 0; }}
QTabBar::tab {{ background: transparent; color: {c['muted']}; font-size: 14px; font-weight: 600; height: 32px;
  padding: 0 16px; margin-right: 6px; border-radius: 16px; }}
QTabBar::tab:selected {{ background: {c['primary-weak']}; color: {c['primary']}; }}

/* Baner ostrzegawczy */
QFrame#banner {{ background: {c['warn-weak']}; border-radius: {RADIUS['card']}px; }}
QFrame#banner QLabel {{ background: transparent; font-size: 15px; }}

/* Toast */
QLabel#toast {{ background: {c['toast-bg']}; color: {c['toast-text']}; padding: 12px 18px; border-radius: {RADIUS['md']}px; font-size: 15px; }}

/* Menu */
QMenu {{ background: {c['card']}; border: 1px solid {c['line']}; border-radius: {RADIUS['md']}px; padding: 6px; }}
QMenu::item {{ padding: 10px 18px 10px 12px; border-radius: 8px; font-weight: 600; font-size: 15px; }}
QMenu::item:selected {{ background: {c['primary-weak']}; }}
QMenu::separator {{ height: 1px; background: {c['line']}; margin: 4px 8px; }}
QMenu::icon {{ padding-left: 8px; }}

/* Okna komunikatów */
QMessageBox {{ background: {c['card']}; }}
QMessageBox QLabel {{ font-size: 16px; }}

/* Pasek postępu (cienki, pod paskiem górnym) */
QProgressBar {{ background: transparent; border: 0; max-height: 3px; min-height: 3px; }}
QProgressBar::chunk {{ background: {c['primary']}; border-radius: 1px; }}

/* Przewijanie */
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle {{ background: {c['line']}; border-radius: 3px; min-height: 30px; min-width: 30px; }}
QScrollBar::handle:hover {{ background: {c['muted']}; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ background: none; width: 0; height: 0; }}
QSplitter::handle {{ background: transparent; }}
"""


def _palette() -> QPalette:
    c = T.colors
    p = QPalette()
    p.setColor(QPalette.Window, QColor(c["bg"]))
    p.setColor(QPalette.WindowText, QColor(c["text"]))
    p.setColor(QPalette.Base, QColor(c["card"]))
    p.setColor(QPalette.AlternateBase, QColor(c["bg"]))
    p.setColor(QPalette.Text, QColor(c["text"]))
    p.setColor(QPalette.Button, QColor(c["card"]))
    p.setColor(QPalette.ButtonText, QColor(c["text"]))
    p.setColor(QPalette.Highlight, QColor(c["primary"]))
    p.setColor(QPalette.HighlightedText, QColor(c["on-primary"]))
    p.setColor(QPalette.Link, QColor(c["primary"]))
    p.setColor(QPalette.PlaceholderText, QColor(c["muted"]))
    p.setColor(QPalette.ToolTipBase, QColor(c["toast-bg"]))
    p.setColor(QPalette.ToolTipText, QColor(c["toast-text"]))
    for role in (QPalette.Text, QPalette.WindowText, QPalette.ButtonText):
        p.setColor(QPalette.Disabled, role, QColor(c["muted"]))
    return p


def system_scheme() -> str:
    try:
        cs = QGuiApplication.styleHints().colorScheme()
        return "dark" if cs == Qt.ColorScheme.Dark else "light"
    except AttributeError:
        return "light"


_listeners: list = []


def on_change(fn):
    _listeners.append(fn)


def apply(app, scheme: str | None = None):
    T.scheme = scheme or system_scheme()
    T.colors = {**(_DARK if T.dark else _LIGHT), **_SHARED}
    app.setStyle("Fusion")
    app.setPalette(_palette())
    f = font(16)
    app.setFont(f)
    app.setStyleSheet(build_qss())
    _refresh_icons()
    for fn in list(_listeners):
        try:
            fn()
        except RuntimeError:
            pass


def follow_system(app):
    """Motyw ciemny włącza się automatycznie razem z ustawieniem systemu."""
    try:
        QGuiApplication.styleHints().colorSchemeChanged.connect(lambda *_: apply(app))
    except AttributeError:
        pass
    if sys.platform == "win32":
        app.setStyle("Fusion")
