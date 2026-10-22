"""Komponenty GUI zgodne z design systemem: karty, wiersze list, badge statusu, toast, pusty stan, dialogi."""
from __future__ import annotations

import traceback
from pathlib import Path

from PySide6.QtCore import (QEasingCurve, QEvent, QObject, QPoint, QPropertyAnimation, QRect, QRunnable, QSize, Qt,
                            QTimer, Signal)
from PySide6.QtGui import (QBrush, QColor, QFont, QFontMetrics, QIcon, QPainter, QPainterPath, QPen, QPixmap,
                           QSyntaxHighlighter, QTextCharFormat)
from PySide6.QtWidgets import (QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit,
                               QPushButton, QStyle, QStyledItemDelegate, QVBoxLayout, QWidget)

from . import icons
from .theme import T, font, on_change


# ====================================================================== wątki
class WorkerSignals(QObject):
    done = Signal(object)
    failed = Signal(str)


class Worker(QRunnable):
    """Uruchamia funkcję w tle (QThreadPool) i zwraca wynik sygnałem w wątku GUI."""

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn, self.args, self.kwargs = fn, args, kwargs
        self.signals = WorkerSignals()
        self.setAutoDelete(False)

    def run(self):
        try:
            result = self.fn(*self.args, **self.kwargs)
        except Exception as e:  # noqa: BLE001
            msg = str(e) or e.__class__.__name__
            if not msg.strip():
                msg = traceback.format_exc()
            self.signals.failed.emit(msg)
            return
        self.signals.done.emit(result)


class LogBus(QObject):
    """Bezpieczne przekazywanie wpisów dziennika z wątków roboczych."""
    message = Signal(str, str)

    def __call__(self, cmd: str, out: str):
        self.message.emit(cmd, out)


# ====================================================================== proste klocki
class Card(QFrame):
    """Karta: tło `card`, promień 14 px, delikatny cień (w ciemnym motywie bez cienia)."""

    def __init__(self, parent=None, padding=(16, 14, 16, 14), spacing=10):
        super().__init__(parent)
        self.setObjectName("card")
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(*padding)
        self.lay.setSpacing(spacing)


def separator() -> QFrame:
    f = QFrame()
    f.setObjectName("sep")
    return f


def label(text: str = "", role: str = "", wrap: bool = False) -> QLabel:
    lb = QLabel(text)
    if role:
        lb.setObjectName(role)
    lb.setWordWrap(wrap)
    return lb


def section_label(text: str) -> QLabel:
    """Nagłówek grupy: WERSALIKI, muted, rozstrzelenie .04em."""
    lb = QLabel(text.upper())
    lb.setObjectName("sectionLabel")
    f = font(14, 700)
    f.setLetterSpacing(QFont.PercentageSpacing, 104)
    lb.setFont(f)
    return lb


def field(title: str, widget: QWidget, hint: str = "") -> QWidget:
    """Pole formularza: etykieta nad polem, opcjonalna podpowiedź pod spodem."""
    w = QWidget()
    v = QVBoxLayout(w)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(6)
    if title:
        v.addWidget(label(title, "fieldLabel"))
    v.addWidget(widget)
    if hint:
        v.addWidget(label(hint, "hint", wrap=True))
    return w


class Btn(QPushButton):
    """Przycisk z odstępem 8 px między ikoną a tekstem."""

    def __init__(self, text: str = "", gap: bool = False):
        super().__init__()
        self._gap = gap
        self.setText(text)

    def setText(self, text: str):
        super().setText((" " + text) if (self._gap and text) else text)


def button(text: str, kind: str = "ghost", icon: str = "", tall: bool = False) -> QPushButton:
    """Przycisk: kind = primary | ghost | danger | dangerGhost | add | link."""
    from .theme import bind_icon
    b = Btn(text, gap=bool(icon))
    if kind != "ghost":
        b.setObjectName(kind)
    elif tall:
        b.setObjectName("tall")
    if kind in ("primary", "danger") and tall:
        b.setMinimumHeight(48)
    b.setCursor(Qt.PointingHandCursor)
    if icon:
        token = {"primary": "on-primary", "danger": "on-danger", "dangerGhost": "danger"}.get(kind, "primary")
        bind_icon(b, icon, token, 20)
        b.setIconSize(QSize(20, 20))
    return b


def icon_button(icon: str, tip: str, token: str = "text") -> QPushButton:
    from .theme import bind_icon
    b = QPushButton()
    b.setObjectName("iconBtn")
    b.setToolTip(tip)
    b.setCursor(Qt.PointingHandCursor)
    bind_icon(b, icon, token, 24)
    b.setIconSize(QSize(24, 24))
    return b


class IconLabel(QLabel):
    """Ikona z zestawu jako QLabel (np. w wierszach informacji)."""

    def __init__(self, name: str, token: str = "primary", size: int = 22, opacity: float = 1.0, parent=None):
        super().__init__(parent)
        self.name, self.token, self.size_, self.opacity = name, token, size, opacity
        self.setFixedSize(size, size)
        self._paint()
        on_change(self._paint)

    def _paint(self):
        self.setPixmap(icons.pixmap(self.name, T[self.token], self.size_, 2.0, self.opacity))


class Badge(QWidget):
    """Status: kropka 8 px i słowo w kolorze statusu (kolor nigdy bez słowa)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.token, self.word = "s-wycena", ""
        self.setFont(font(13, 600))

    def set(self, token: str, word: str):
        self.token, self.word = token, word
        self.updateGeometry()
        self.update()
        self.setVisible(bool(word))

    def sizeHint(self):
        fm = QFontMetrics(self.font())
        return QSize(14 + fm.horizontalAdvance(self.word) + 2, max(20, fm.height()))

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        paint_badge(p, QPoint(0, self.height() // 2), self.token, self.word, self.font())


def paint_badge(p: QPainter, left_mid: QPoint, token: str, word: str, f: QFont) -> int:
    col = T.q(token)
    p.save()
    p.setPen(Qt.NoPen)
    p.setBrush(col)
    p.drawEllipse(QRect(left_mid.x(), left_mid.y() - 4, 8, 8))
    p.setPen(col)
    p.setFont(f)
    fm = QFontMetrics(f)
    x = left_mid.x() + 14
    p.drawText(QRect(x, left_mid.y() - fm.height() // 2, fm.horizontalAdvance(word) + 2, fm.height()),
               Qt.AlignVCenter | Qt.AlignLeft, word)
    p.restore()
    return 14 + fm.horizontalAdvance(word)


def badge_width(word: str, f: QFont) -> int:
    return 14 + QFontMetrics(f).horizontalAdvance(word)


class Banner(QFrame):
    """Baner ostrzegawczy: tło warn-weak, ikona warn, kluczowy fragment pogrubiony w kolorze warn."""

    def __init__(self, html: str, parent=None):
        super().__init__(parent)
        self.setObjectName("banner")
        h = QHBoxLayout(self)
        h.setContentsMargins(14, 10, 10, 10)
        h.setSpacing(10)
        h.addWidget(IconLabel("warn", "warn", 22))
        self.text = QLabel()
        self.text.setWordWrap(True)
        self.text.setTextFormat(Qt.RichText)
        self.html = html
        h.addWidget(self.text, 1)
        self.actions = h
        self._paint()
        on_change(self._paint)

    def _paint(self):
        self.text.setText(self.html.replace("<b>", f"<b style='color:{T['warn']}'>"))


class EmptyState(QWidget):
    """Pusty stan: ikona 56 px (opacity .5), tekst muted i opcjonalny przycisk."""

    def __init__(self, icon: str, title: str, text: str = "", parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 48, 24, 48)
        v.setSpacing(8)
        v.addStretch(1)
        self.icon = IconLabel(icon, "muted", 56, 0.5)
        v.addWidget(self.icon, 0, Qt.AlignHCenter)
        self.title = label(title, "cardTitle")
        self.title.setAlignment(Qt.AlignCenter)
        v.addWidget(self.title)
        self.text = label(text, "emptyText", wrap=True)
        self.text.setAlignment(Qt.AlignCenter)
        self.text.setVisible(bool(text))
        v.addWidget(self.text)
        self.btns = QHBoxLayout()
        self.btns.setSpacing(10)
        self.btns.addStretch(1)
        self.btns.addStretch(1)
        v.addSpacing(8)
        v.addLayout(self.btns)
        v.addStretch(2)

    def add_button(self, b: QPushButton):
        self.btns.insertWidget(self.btns.count() - 1, b)

    def set_text(self, title: str, text: str = "", icon: str = ""):
        self.title.setText(title)
        self.text.setText(text)
        self.text.setVisible(bool(text))
        if icon and icon != self.icon.name:
            self.icon.name = icon
            self.icon._paint()


class Toast(QLabel):
    """Krótkie potwierdzenie u góry okna (ciemne w obu motywach, 0,2 s)."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("toast")
        self.setAlignment(Qt.AlignCenter)
        self.effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.effect)
        self.anim = QPropertyAnimation(self.effect, b"opacity", self)
        self.anim.setDuration(200)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._fade_out)
        self.anim.finished.connect(self._anim_done)
        self.top = 12
        self.hide()

    def show_message(self, text: str, ms: int = 2600):
        self.setText(text)
        self.adjustSize()
        self._place()
        self.raise_()
        start = self.effect.opacity() if self.isVisible() else 0.0
        self.show()
        self.anim.stop()
        self.anim.setStartValue(start)
        self.anim.setEndValue(1.0)
        self.anim.start()
        self.timer.start(ms)

    def _place(self):
        pw = self.parent().width()
        self.move((pw - self.width()) // 2, self.top)

    def _fade_out(self):
        self.anim.stop()
        self.anim.setStartValue(1.0)
        self.anim.setEndValue(0.0)
        self.anim.start()

    def _anim_done(self):
        if self.anim.endValue() == 0.0:
            self.hide()


# ====================================================================== dialogi komunikatów
def _repolish(w):
    w.style().unpolish(w)
    w.style().polish(w)


def _box(parent, title: str, text: str) -> QMessageBox:
    m = QMessageBox(parent)
    m.setWindowTitle(title)
    m.setText(text)
    m.setIcon(QMessageBox.NoIcon)
    m.setTextInteractionFlags(Qt.TextSelectableByMouse)
    return m


def ask(parent, title: str, text: str, ok: str, cancel: str = "Anuluj", danger: bool = False) -> bool:
    """Potwierdzenie: główna akcja (czasownik) + „Anuluj”."""
    m = _box(parent, title, text)
    b_cancel = m.addButton(cancel, QMessageBox.RejectRole)
    b_ok = m.addButton(ok, QMessageBox.AcceptRole)
    b_ok.setObjectName("danger" if danger else "primary")
    _repolish(b_ok)
    for b in (b_ok, b_cancel):
        b.setMinimumWidth(120)
        b.setMinimumHeight(44)
    m.setDefaultButton(b_cancel if danger else b_ok)
    m.exec()
    return m.clickedButton() is b_ok


def choose(parent, title: str, text: str, options: list[str], primary: int = 0) -> int:
    """Wybór jednej z kilku akcji; zwraca indeks albo -1 (Anuluj)."""
    m = _box(parent, title, text)
    m.addButton("Anuluj", QMessageBox.RejectRole).setMinimumHeight(44)
    btns = []
    for i, o in enumerate(options):
        b = m.addButton(o, QMessageBox.AcceptRole)
        b.setMinimumHeight(44)
        if i == primary:
            b.setObjectName("primary")
            _repolish(b)
            m.setDefaultButton(b)
        btns.append(b)
    m.exec()
    return btns.index(m.clickedButton()) if m.clickedButton() in btns else -1


def notify(parent, title: str, text: str):
    m = _box(parent, title, text)
    b = m.addButton("OK", QMessageBox.AcceptRole)
    b.setObjectName("primary")
    _repolish(b)
    b.setMinimumSize(120, 44)
    m.exec()


# ====================================================================== podgląd różnic
class DiffHighlighter(QSyntaxHighlighter):
    def __init__(self, doc):
        super().__init__(doc)
        self.update_colors()

    def update_colors(self):
        def fmt(fg, bg=None, bold=False):
            f = QTextCharFormat()
            f.setForeground(QColor(fg))
            if bg:
                f.setBackground(QColor(bg))
            if bold:
                f.setFontWeight(QFont.Bold)
            return f
        self.add = fmt(T["ok-text"], T["ok-weak"])
        self.rem = fmt(T["danger"], T["danger-weak"])
        self.hunk = fmt(T["primary"], T["primary-weak"])
        self.meta = fmt(T["muted"], bold=True)

    def highlightBlock(self, text: str):
        if text.startswith(("+++", "---", "diff ", "index ", "commit ", "new file", "deleted file", "Nowy plik")):
            self.setFormat(0, len(text), self.meta)
        elif text.startswith("+"):
            self.setFormat(0, len(text), self.add)
        elif text.startswith("-"):
            self.setFormat(0, len(text), self.rem)
        elif text.startswith("@@"):
            self.setFormat(0, len(text), self.hunk)


class GitignoreHighlighter(QSyntaxHighlighter):
    """Kolorowanie .gitignore: komentarze muted, wyjątki (!) w primary, foldery pogrubione."""

    def __init__(self, doc):
        super().__init__(doc)
        self.update_colors()

    def update_colors(self):
        self.comment = QTextCharFormat()
        self.comment.setForeground(T.q("muted"))
        self.header = QTextCharFormat(self.comment)
        self.header.setFontWeight(QFont.Bold)
        self.neg = QTextCharFormat()
        self.neg.setForeground(T.q("primary"))
        self.neg.setFontWeight(QFont.Bold)
        self.dir = QTextCharFormat()
        self.dir.setFontWeight(QFont.DemiBold)

    def highlightBlock(self, text: str):
        t = text.strip()
        if t.startswith("# ====="):
            self.setFormat(0, len(text), self.header)
        elif t.startswith("#"):
            self.setFormat(0, len(text), self.comment)
        elif t.startswith("!"):
            self.setFormat(0, len(text), self.neg)
        elif t.endswith("/"):
            self.setFormat(0, len(text), self.dir)


class DiffView(QPlainTextEdit):
    def __init__(self, parent=None, highlight: bool = True):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.setFont(font(14, 400, mono=True))
        self.setFrameShape(QFrame.NoFrame)
        self._hl = DiffHighlighter(self.document()) if highlight else None
        on_change(self._recolor)

    def _recolor(self):
        if self._hl:
            self._hl.update_colors()
            self._hl.rehighlight()

    def show_text(self, text: str, limit: int = 400_000):
        if len(text) > limit:
            text = text[:limit] + "\n\n… (podgląd obcięty)"
        self.setPlainText(text)


# ====================================================================== wiersze list (delegaty)
ROLE_DATA = Qt.UserRole
ROLE_META = Qt.UserRole + 1


class _RowDelegate(QStyledItemDelegate):
    pad_x = 16

    def _bg(self, p, opt, index):
        r = opt.rect
        selected = bool(opt.state & QStyle.State_Selected)
        hover = bool(opt.state & QStyle.State_MouseOver)
        if selected:
            p.fillRect(r, T.q("primary-weak"))
            p.fillRect(QRect(r.left(), r.top(), 3, r.height()), T.q("primary"))
        elif hover:
            c = T.q("line")
            c.setAlpha(110)
            p.fillRect(r, c)
        if index.row() < index.model().rowCount() - 1:
            p.fillRect(QRect(r.left() + self.pad_x, r.bottom(), r.width() - self.pad_x, 1), T.q("line"))

    @staticmethod
    def _text(p, rect, text, f, color, align=Qt.AlignLeft | Qt.AlignVCenter):
        p.setFont(f)
        p.setPen(color)
        el = QFontMetrics(f).elidedText(text, Qt.ElideMiddle if "/" in text or "\\" in text else Qt.ElideRight,
                                        rect.width())
        p.drawText(rect, align, el)


class ProjectDelegate(_RowDelegate):
    """Karta projektu: nazwa (card-title), ścieżka (secondary), status + metadane (caption)."""

    def sizeHint(self, opt, index):
        return QSize(200, 82)

    def paint(self, p, opt, index):
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        self._bg(p, opt, index)
        path = index.data(ROLE_DATA) or ""
        meta = index.data(ROLE_META) or {}
        r = opt.rect.adjusted(self.pad_x, 12, -12, -12)
        self._text(p, QRect(r.left(), r.top(), r.width(), 22), Path(path).name or path, font(17, 700), T.q("text"))
        self._text(p, QRect(r.left(), r.top() + 23, r.width(), 18), path, font(14), T.q("muted"))
        y = r.top() + 49
        bf = font(13, 600)
        w = paint_badge(p, QPoint(r.left(), y), meta.get("token", "s-wycena"), meta.get("word", "sprawdzanie…"), bf)
        if meta.get("meta"):
            self._text(p, QRect(r.left() + w + 6, y - 9, r.width() - w - 6, 18), "·  " + meta["meta"], font(13),
                       T.q("muted"))
        p.restore()


class RepoDelegate(_RowDelegate):
    """Repozytorium z GitHuba: nazwa, opis, metadane łączone kropką."""

    def sizeHint(self, opt, index):
        r = index.data(ROLE_DATA)
        return QSize(200, 80 if r and r.description else 60)

    def paint(self, p, opt, index):
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        self._bg(p, opt, index)
        repo = index.data(ROLE_DATA)
        r = opt.rect.adjusted(self.pad_x, 10, -12, -10)
        self._text(p, QRect(r.left(), r.top(), r.width(), 21), repo.full_name, font(16, 600), T.q("text"))
        y = r.top() + 22
        if repo.description:
            self._text(p, QRect(r.left(), y, r.width(), 19), repo.description, font(14), T.q("muted"))
            y += 20
        meta = " · ".join(x for x in ("prywatne" if repo.private else "publiczne", fmt_date(repo.updated_at),
                                       "puste" if repo.empty else "") if x)
        self._text(p, QRect(r.left(), y, r.width(), 18), meta, font(13), T.q("muted"))
        p.restore()


KIND_TOKENS = {
    "nowy": "s-zakonczony", "dodany": "s-zakonczony", "zmieniony": "s-w_trakcie",
    "usunięty": "danger", "konflikt": "danger", "przeniesiony": "primary", "usunięty z repo": "s-wycena",
}


class FileDelegate(_RowDelegate):
    """Wiersz zmienionego pliku: pole wyboru, nazwa pliku + folder, status słowem."""
    pad_x = 12

    def sizeHint(self, opt, index):
        return QSize(200, 46)

    def _check_rect(self, rect: QRect) -> QRect:
        return QRect(rect.left() + 12, rect.center().y() - 10, 20, 20)

    def paint(self, p, opt, index):
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        self._bg(p, opt, index)
        change = index.data(ROLE_DATA)
        checked = is_checked(index.data(Qt.CheckStateRole))
        cr = self._check_rect(opt.rect)
        path = QPainterPath()
        path.addRoundedRect(cr.adjusted(1, 1, -1, -1), 6, 6)
        if checked:
            p.fillPath(path, T.q("primary"))
            p.drawPixmap(cr.adjusted(3, 3, -3, -3), icons.pixmap("check", T["on-primary"], 14))
        else:
            p.fillPath(path, T.q("card"))
            p.setPen(QPen(T.q("line"), 2))
            p.drawPath(path)
        bf = font(13, 600)
        bw = badge_width(change.kind, bf)
        paint_badge(p, QPoint(opt.rect.right() - 12 - bw, opt.rect.center().y()), KIND_TOKENS.get(change.kind, "muted"),
                    change.kind, bf)
        x = cr.right() + 12
        avail = opt.rect.right() - 24 - bw - x
        pth = change.path.replace("\\", "/")
        folder, _, name = pth.rpartition("/")
        nf = font(15, 600)
        nw = min(QFontMetrics(nf).horizontalAdvance(name) + 2, avail)
        self._text(p, QRect(x, opt.rect.top(), nw, opt.rect.height()), name, nf, T.q("text"))
        extra = folder + "/" if folder else ""
        if change.orig_path:
            extra = f"← {change.orig_path}  " + extra
        if extra and avail - nw > 30:
            self._text(p, QRect(x + nw + 8, opt.rect.top(), avail - nw - 8, opt.rect.height()), extra, font(13),
                       T.q("muted"))
        p.restore()

    def editorEvent(self, event, model, opt, index):
        if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
            if self._check_rect(opt.rect).adjusted(-8, -8, 8, 8).contains(event.position().toPoint()):
                self._toggle(model, index)
                return True
        if event.type() == QEvent.MouseButtonDblClick:
            self._toggle(model, index)
            return True
        if event.type() == QEvent.KeyPress and event.key() == Qt.Key_Space:
            self._toggle(model, index)
            return True
        return False

    @staticmethod
    def _toggle(model, index):
        on = is_checked(index.data(Qt.CheckStateRole))
        model.setData(index, Qt.Unchecked if on else Qt.Checked, Qt.CheckStateRole)


def is_checked(v) -> bool:
    if v is None:
        return False
    return v == Qt.Checked or getattr(v, "value", v) == Qt.Checked.value


def fmt_date(iso: str) -> str:
    """RRRR-MM-DD → DD.MM.RRRR"""
    if len(iso) >= 10 and iso[4] == "-":
        return f"{iso[8:10]}.{iso[5:7]}.{iso[0:4]}"
    return iso


# ====================================================================== ikona aplikacji
def app_icon() -> QIcon:
    """Znak rodziny: kwadrat `primary` z zaokrąglonymi rogami, symbol gałęzi w kolorze `brand-bolt`."""
    ic = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        s = size / 64
        p.setBrush(QBrush(QColor("#1d4ed8")))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(QRect(0, 0, size, size), 14 * s, 14 * s)
        bolt = QColor("#ffc828")
        pen = QPen(bolt, max(1.5, 5 * s))
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawLine(int(23 * s), int(18 * s), int(23 * s), int(46 * s))
        path = QPainterPath()
        path.moveTo(23 * s, 38 * s)
        path.cubicTo(23 * s, 28 * s, 41 * s, 32 * s, 41 * s, 22 * s)
        p.drawPath(path)
        p.setPen(Qt.NoPen)
        p.setBrush(bolt)
        for x, y in ((23, 16), (23, 48), (41, 18)):
            rr = 6.5 * s
            p.drawEllipse(int(x * s - rr), int(y * s - rr), int(2 * rr), int(2 * rr))
        p.end()
        ic.addPixmap(pm)
    return ic
