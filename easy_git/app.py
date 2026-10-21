"""Główne okno aplikacji EasyGit."""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from PySide6.QtCore import QEvent, QSize, Qt, QThreadPool, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QButtonGroup, QCheckBox, QFileDialog, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMenu,
                               QPlainTextEdit, QProgressBar, QSplitter, QStackedWidget, QTableWidget,
                               QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from . import __version__, icons, theme
from .config import Config, delete_token, load_token, save_token
from .dialogs import CloneDialog, CreateRepoDialog, GitignoreDialog, LinkDialog, LoginDialog
from .git_ops import GITHUB_LIMIT_BYTES, Repo, RepoInfo, clone, git_version
from .github_api import GitHub
from .theme import T, font
from .widgets import (KIND_TOKENS, ROLE_DATA, ROLE_META, Badge, Banner, Card, DiffView, EmptyState, FileDelegate,
                      IconLabel, LogBus, ProjectDelegate, RepoDelegate, Toast, Worker, app_icon, ask, button, choose,
                      icon_button, label, notify, section_label, separator)


def plural_zmian(n: int) -> str:
    if n == 1:
        return "1 zmiana"
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return f"{n} zmiany"
    return f"{n} zmian"


def plural_commit(n: int) -> str:
    if n == 1:
        return "1 commit"
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return f"{n} commity"
    return f"{n} commitów"


def status_of(info: RepoInfo | None, exists: bool = True) -> tuple[str, str]:
    """Status projektu jako (token koloru, słowo)."""
    if not exists:
        return theme.STATUS_NEUTRAL, "brak folderu"
    if not info or not info.is_repo:
        return theme.STATUS_NEUTRAL, "nie jest repozytorium"
    if info.merging:
        return "danger", "scalanie – konflikt"
    if info.changes:
        return theme.STATUS_CHANGES, plural_zmian(len(info.changes))
    if info.ahead:
        return theme.STATUS_OUTGOING, f"{info.ahead} do wysłania"
    if info.behind:
        return theme.STATUS_OUTGOING, f"{info.behind} do pobrania"
    if not info.remote_url:
        return theme.STATUS_NEUTRAL, "bez GitHuba"
    if not info.has_commits:
        return theme.STATUS_NEUTRAL, "brak commitów"
    if not info.upstream:
        return theme.STATUS_OUTGOING, "do wysłania"
    return theme.STATUS_SYNCED, "aktualny"


def friendly_error(msg: str) -> str:
    low = msg.lower()
    hints = []
    if "fetch first" in low or "non-fast-forward" in low or "[rejected]" in low:
        hints.append("Na GitHubie są nowsze zmiany. Kliknij „Pobierz”, a potem wyślij ponownie.")
    if "permission to" in low and "denied" in low or "403" in low:
        hints.append("Token nie ma uprawnień do zapisu w tym repozytorium. Utwórz nowy token (klasyczny z "
                     "uprawnieniem repo albo fine-grained z dostępem Contents: Read and write do tego "
                     "repozytorium), wyloguj się i zaloguj ponownie.")
    elif "authentication failed" in low or "could not read username" in low or "401" in low:
        hints.append("Nie udało się zalogować do GitHuba. Token mógł wygasnąć – zaloguj się ponownie.")
    if "repository not found" in low:
        hints.append("Nie znaleziono repozytorium – sprawdź adres i czy token ma do niego dostęp.")
    if "would be overwritten" in low:
        hints.append("Masz niezatwierdzone zmiany w tych plikach. Najpierw je zatwierdź albo cofnij.")
    if "conflict" in low:
        hints.append("Wystąpił konflikt. Otwórz pliki oznaczone jako konflikt, popraw fragmenty między "
                     "<<<<<<< a >>>>>>> i zatwierdź.")
    if "please tell me who you are" in low:
        hints.append("Zaloguj się do GitHuba – aplikacja użyje nazwy i adresu z konta.")
    if "unrelated histories" in low:
        hints.append("Lokalna i zdalna historia nie mają wspólnego początku.")
    if "exceeds github's file size limit" in low or "large files" in low:
        hints.append("Plik jest większy niż 100 MB – dodaj go do .gitignore.")
    if hints:
        return "\n".join(hints) + "\n\nSzczegóły:\n" + msg
    return msg


def card_head(*widgets, right=None) -> QWidget:
    """Nagłówek sekcji karty (jak .sec-head): tekst po lewej, akcja po prawej."""
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(16, 8, 12, 8)
    h.setSpacing(10)
    for x in widgets:
        h.addWidget(x)
    h.addStretch(1)
    if right is not None:
        h.addWidget(right)
    w.setMinimumHeight(52)
    return w


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("EasyGit")
        self.setWindowIcon(app_icon())
        self.resize(1320, 840)
        self.setMinimumSize(980, 640)
        self.cfg = Config()
        self.pool = QThreadPool.globalInstance()
        self.workers: set[Worker] = set()
        self.busy = 0
        self.token = load_token()
        self.user = None
        self.gh_repos = []
        self.current: str = ""
        self.info: RepoInfo | None = None
        self.last_fetch: dict[str, float] = {}
        self.logbus = LogBus()
        self.logbus.message.connect(self._append_log)

        self._build_ui()
        theme.on_change(self._on_theme)
        self.reload_projects()
        QTimer.singleShot(100, self._startup)

    # ================================================================ UI
    def _build_ui(self):
        screen = QWidget()
        screen.setObjectName("screen")
        root = QVBoxLayout(screen)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.setCentralWidget(screen)

        # ---- pasek górny
        top = QWidget()
        top.setObjectName("topbar")
        th = QHBoxLayout(top)
        th.setContentsMargins(16, 10, 16, 8)
        th.setSpacing(10)
        logo = QLabel()
        logo.setPixmap(app_icon().pixmap(32, 32))
        th.addWidget(logo)
        th.addWidget(label("EasyGit", "screenTitle"))
        th.addStretch(1)
        b = button("Powiąż folder", "ghost", "folder")
        b.setToolTip("Połącz folder na dysku z repozytorium na GitHubie")
        b.clicked.connect(lambda: self.link_folder())
        th.addWidget(b)
        b = button("Sklonuj", "ghost", "download")
        b.setToolTip("Pobierz repozytorium z GitHuba do nowego folderu")
        b.clicked.connect(lambda: self.clone_repo())
        th.addWidget(b)
        b = button("Nowe repozytorium", "primary", "plus")
        b.clicked.connect(lambda: self.create_repo())
        th.addWidget(b)
        self.btn_refresh = icon_button("refresh", "Odśwież (F5)")
        self.btn_refresh.clicked.connect(self.refresh_all)
        th.addWidget(self.btn_refresh)
        self.btn_account = button("Zaloguj do GitHuba", "ghost")
        self.btn_account.setObjectName("account")
        self.btn_account.setMinimumHeight(40)
        self.btn_account.clicked.connect(self._account_clicked)
        th.addWidget(self.btn_account)
        root.addWidget(top)
        QShortcut(QKeySequence("F5"), self, self.refresh_all)

        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        root.addWidget(self.progress)

        body = QWidget()
        bl = QHBoxLayout(body)
        bl.setContentsMargins(12, 6, 12, 12)
        split = QSplitter(Qt.Horizontal)
        split.setHandleWidth(12)
        split.setChildrenCollapsible(False)
        bl.addWidget(split)
        root.addWidget(body, 1)

        split.addWidget(self._build_left())
        split.addWidget(self._build_right())
        split.setSizes([340, 960])
        split.setStretchFactor(1, 1)

        self.toast = Toast(screen)
        self.toast.top = 12

    def _build_left(self) -> QWidget:
        w = QWidget()
        w.setMinimumWidth(300)
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)

        seg = QHBoxLayout()
        seg.setSpacing(6)
        self.seg_group = QButtonGroup(self)
        for i, text in enumerate(("Moje projekty", "GitHub")):
            b = button(text)
            b.setObjectName("seg")
            b.setMinimumHeight(38)
            b.setCheckable(True)
            self.seg_group.addButton(b, i)
            seg.addWidget(b)
        self.seg_group.button(0).setChecked(True)
        v.addLayout(seg)

        self.left_stack = QStackedWidget()
        self.seg_group.idClicked.connect(self.left_stack.setCurrentIndex)
        v.addWidget(self.left_stack, 1)

        # --- projekty
        pc = Card(padding=(0, 0, 0, 0), spacing=0)
        self.proj_stack = QStackedWidget()
        self.proj_list = QListWidget()
        self.proj_list.setItemDelegate(ProjectDelegate(self.proj_list))
        self.proj_list.setMouseTracking(True)
        self.proj_list.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.proj_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.proj_list.customContextMenuRequested.connect(self._project_menu)
        self.proj_list.currentItemChanged.connect(self._project_selected)
        self.proj_stack.addWidget(self.proj_list)
        self.proj_empty = EmptyState("folder", "Brak projektów",
                                     "Dodaj folder albo sklonuj repozytorium – pojawi się tutaj.")
        self.proj_stack.addWidget(self.proj_empty)
        pc.lay.addWidget(self.proj_stack, 1)
        pc.lay.addWidget(separator())
        foot = QHBoxLayout()
        foot.setContentsMargins(8, 6, 8, 6)
        b = button("Dodaj folder", "add", "plus")
        b.setToolTip("Dodaj do listy folder z projektem")
        b.clicked.connect(self.add_existing_folder)
        foot.addWidget(b)
        foot.addStretch(1)
        self.btn_proj_more = icon_button("more", "Więcej opcji projektu", "muted")
        self.btn_proj_more.clicked.connect(lambda: self._project_menu(None, anchor=self.btn_proj_more))
        foot.addWidget(self.btn_proj_more)
        pc.lay.addLayout(foot)
        self.left_stack.addWidget(pc)

        # --- GitHub
        gw = QWidget()
        gv = QVBoxLayout(gw)
        gv.setContentsMargins(0, 0, 0, 0)
        gv.setSpacing(10)
        self.gh_filter = QLineEdit()
        self.gh_filter.setObjectName("search")
        self.gh_filter.setPlaceholderText("Szukaj repozytorium")
        self._search_action = self.gh_filter.addAction(icons.icon("search", T["muted"], 22),
                                                       QLineEdit.LeadingPosition)
        self.gh_filter.textChanged.connect(self._fill_gh_list)
        gv.addWidget(self.gh_filter)
        gc = Card(padding=(0, 0, 0, 0), spacing=0)
        self.gh_stack = QStackedWidget()
        self.gh_list = QListWidget()
        self.gh_list.setItemDelegate(RepoDelegate(self.gh_list))
        self.gh_list.setMouseTracking(True)
        self.gh_list.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.gh_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.gh_list.customContextMenuRequested.connect(self._gh_menu)
        self.gh_list.itemDoubleClicked.connect(lambda it: self._gh_menu(None, it))
        self.gh_stack.addWidget(self.gh_list)
        self.gh_empty = EmptyState("share", "Zaloguj się do GitHuba", "Zobaczysz tu swoje repozytoria.")
        b = button("Zaloguj", "primary")
        b.clicked.connect(self.login)
        self.gh_empty.add_button(b)
        self.gh_stack.addWidget(self.gh_empty)
        self.gh_stack.setCurrentIndex(1)
        gc.lay.addWidget(self.gh_stack, 1)
        gc.lay.addWidget(separator())
        foot = QHBoxLayout()
        foot.setContentsMargins(8, 6, 8, 6)
        foot.setSpacing(2)
        for text, ic, slot in (("Sklonuj", "download", self._gh_clone), ("Powiąż", "folder", self._gh_link),
                               ("Otwórz", "share", self._gh_open)):
            b = button(text, "add", ic)
            b.clicked.connect(slot)
            foot.addWidget(b)
        foot.addStretch(1)
        gc.lay.addLayout(foot)
        gv.addWidget(gc, 1)
        self.left_stack.addWidget(gw)
        return w

    def _build_right(self) -> QWidget:
        self.right_stack = QStackedWidget()

        # --- pusty stan
        ec = Card()
        self.right_empty = EmptyState("folder", "Wybierz projekt",
                                      "Powiąż folder z repozytorium na GitHubie albo sklonuj repozytorium.")
        b = button("Powiąż folder", "primary", "folder")
        b.clicked.connect(lambda: self.link_folder())
        self.right_empty.add_button(b)
        b = button("Sklonuj", "ghost", "download")
        b.clicked.connect(lambda: self.clone_repo())
        self.right_empty.add_button(b)
        ec.lay.addWidget(self.right_empty)
        self.right_stack.addWidget(ec)

        # --- projekt
        pw = QWidget()
        pv = QVBoxLayout(pw)
        pv.setContentsMargins(0, 0, 0, 0)
        pv.setSpacing(12)

        head = Card(padding=(0, 0, 0, 0), spacing=0)
        r1 = QHBoxLayout()
        r1.setContentsMargins(16, 10, 10, 0)
        r1.setSpacing(12)
        self.h_name = label("", "screenTitle")
        r1.addWidget(self.h_name)
        self.h_badge = Badge()
        r1.addWidget(self.h_badge)
        r1.addStretch(1)
        b = icon_button("folder", "Otwórz folder", "primary")
        b.clicked.connect(lambda: self._open_path(self.current))
        r1.addWidget(b)
        self.btn_head_more = icon_button("more", "Więcej opcji", "muted")
        self.btn_head_more.clicked.connect(lambda: self._project_menu(None, anchor=self.btn_head_more))
        r1.addWidget(self.btn_head_more)
        head.lay.addLayout(r1)
        self.h_path = label("", "secondary")
        self.h_path.setContentsMargins(16, 0, 16, 10)
        self.h_path.setTextInteractionFlags(Qt.TextSelectableByMouse)
        head.lay.addWidget(self.h_path)
        head.lay.addWidget(separator())

        def irow(icon_name):
            row = QHBoxLayout()
            row.setContentsMargins(16, 9, 16, 9)
            row.setSpacing(12)
            row.addWidget(IconLabel(icon_name, "primary", 22))
            lb = QLabel()
            lb.setTextFormat(Qt.RichText)
            lb.setOpenExternalLinks(True)
            lb.setTextInteractionFlags(Qt.TextBrowserInteraction)
            row.addWidget(lb, 1)
            head.lay.addLayout(row)
            head.lay.addWidget(separator())
            return lb

        self.h_remote = irow("share")
        self.h_branch = irow("cable")
        acts = QHBoxLayout()
        acts.setContentsMargins(12, 10, 12, 12)
        acts.setSpacing(8)
        self.btn_pull = button("Pobierz", "ghost", "download")
        self.btn_pull.setToolTip("Pobierz zmiany z GitHuba (pull)")
        self.btn_pull.clicked.connect(self.pull)
        self.btn_push = button("Wyślij", "ghost", "upload")
        self.btn_push.setToolTip("Wyślij zatwierdzone zmiany na GitHuba (push)")
        self.btn_push.clicked.connect(self.push)
        self.btn_ignore = button(".gitignore", "ghost", "edit")
        self.btn_ignore.clicked.connect(self.edit_gitignore)
        self.btn_web = button("Otwórz na GitHubie", "ghost", "share")
        self.btn_web.clicked.connect(self._open_current_web)
        for x in (self.btn_pull, self.btn_push, self.btn_ignore, self.btn_web):
            acts.addWidget(x)
        acts.addStretch(1)
        head.lay.addLayout(acts)
        pv.addWidget(head)

        self.merge_bar = Banner("Trwa <b>scalanie</b> zmian z GitHubem. Popraw pliki oznaczone jako konflikt "
                                "i zatwierdź wszystkie zmiany albo przerwij scalanie.")
        b = button("Przerwij scalanie", "dangerGhost")
        b.clicked.connect(self.abort_merge)
        self.merge_bar.actions.addWidget(b)
        self.merge_bar.hide()
        pv.addWidget(self.merge_bar)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.tabBar().setIconSize(QSize(18, 18))
        pv.addWidget(self.tabs, 1)

        # Zmiany
        chw = QWidget()
        cv = QVBoxLayout(chw)
        cv.setContentsMargins(0, 8, 0, 0)
        sp = QSplitter(Qt.Horizontal)
        sp.setHandleWidth(12)
        sp.setChildrenCollapsible(False)
        lc = Card(padding=(0, 0, 0, 0), spacing=0)
        lc.setMinimumWidth(390)
        self.chk_all = QCheckBox("Wszystkie")
        self.chk_all.clicked.connect(self._toggle_all)
        self.sel_count = label("", "caption")
        lc.lay.addWidget(card_head(section_label("Zmiany"), self.sel_count, right=self.chk_all))
        lc.lay.addWidget(separator())
        self.files = QListWidget()
        self.files.setItemDelegate(FileDelegate(self.files))
        self.files.setMouseTracking(True)
        self.files.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.files.setContextMenuPolicy(Qt.CustomContextMenu)
        self.files.customContextMenuRequested.connect(self._file_menu)
        self.files.currentItemChanged.connect(self._file_selected)
        self.files.itemChanged.connect(self._update_commit_buttons)
        lc.lay.addWidget(self.files, 1)
        lc.lay.addWidget(separator())
        commit_box = QVBoxLayout()
        commit_box.setContentsMargins(14, 12, 14, 14)
        commit_box.setSpacing(6)
        commit_box.addWidget(label("Opis zmian", "fieldLabel"))
        self.msg = QPlainTextEdit()
        self.msg.setObjectName("inp")
        self.msg.setPlaceholderText("np. Dodano obsługę czujnika B12")
        self.msg.setFixedHeight(76)
        self.msg.setFont(font(16))
        self.msg.textChanged.connect(self._update_commit_buttons)
        commit_box.addWidget(self.msg)
        commit_box.addSpacing(6)
        bh = QHBoxLayout()
        bh.setSpacing(10)
        self.btn_commit = button("Zatwierdź", "ghost", "check", tall=True)
        self.btn_commit.setToolTip("Zapisz zmiany w historii lokalnie (commit), bez wysyłania")
        self.btn_commit.clicked.connect(lambda: self.commit(push=False))
        self.btn_commit_push = button("Zatwierdź i wyślij", "primary", "upload", tall=True)
        self.btn_commit_push.clicked.connect(lambda: self.commit(push=True))
        bh.addWidget(self.btn_commit)
        bh.addWidget(self.btn_commit_push, 1)
        commit_box.addLayout(bh)
        lc.lay.addLayout(commit_box)
        sp.addWidget(lc)

        rc = Card(padding=(0, 0, 0, 0), spacing=0)
        self.diff_title = QLabel()
        self.diff_title.setFont(font(16, 600))
        self.diff_badge = Badge()
        rc.lay.addWidget(card_head(self.diff_title, self.diff_badge))
        rc.lay.addWidget(separator())
        self.diff_stack = QStackedWidget()
        self.diff = DiffView()
        self.diff_stack.addWidget(self.diff)
        self.diff_empty = EmptyState("box", "Brak zmian", "Wszystko jest zatwierdzone.")
        self.empty_push = button("Wyślij na GitHuba", "primary", "upload")
        self.empty_push.clicked.connect(self.push)
        self.empty_pull = button("Pobierz z GitHuba", "primary", "download")
        self.empty_pull.clicked.connect(self.pull)
        self.diff_empty.add_button(self.empty_push)
        self.diff_empty.add_button(self.empty_pull)
        self.empty_push.hide()
        self.empty_pull.hide()
        self.diff_stack.addWidget(self.diff_empty)
        rc.lay.addWidget(self.diff_stack, 1)
        sp.addWidget(rc)
        sp.setSizes([430, 530])
        sp.setStretchFactor(1, 1)
        cv.addWidget(sp)
        self.tabs.addTab(chw, "Zmiany")

        # Historia
        hw = QWidget()
        hv = QVBoxLayout(hw)
        hv.setContentsMargins(0, 8, 0, 0)
        sp2 = QSplitter(Qt.Vertical)
        sp2.setHandleWidth(12)
        sp2.setChildrenCollapsible(False)
        tc = Card(padding=(0, 0, 0, 0), spacing=0)
        self.hist = QTableWidget(0, 4)
        self.hist.setHorizontalHeaderLabels(["COMMIT", "DATA", "AUTOR", "OPIS"])
        self.hist.verticalHeader().hide()
        self.hist.verticalHeader().setDefaultSectionSize(40)
        self.hist.setShowGrid(False)
        self.hist.setFont(font(14))
        self.hist.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.hist.setSelectionMode(QAbstractItemView.SingleSelection)
        self.hist.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.hist.setFocusPolicy(Qt.NoFocus)
        hh = self.hist.horizontalHeader()
        hh.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        hh.setHighlightSections(False)
        for i in range(3):
            hh.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.Stretch)
        self.hist.currentCellChanged.connect(self._commit_selected)
        tc.lay.addWidget(self.hist)
        sp2.addWidget(tc)
        dc = Card(padding=(4, 4, 4, 4))
        self.hist_diff = DiffView()
        dc.lay.addWidget(self.hist_diff)
        sp2.addWidget(dc)
        sp2.setSizes([300, 420])
        hv.addWidget(sp2)
        self.tabs.addTab(hw, "Historia")

        # Dziennik
        lw = QWidget()
        lv = QVBoxLayout(lw)
        lv.setContentsMargins(0, 8, 0, 0)
        lcard = Card(padding=(4, 4, 4, 4))
        self.log = DiffView(highlight=False)
        self.log.setFont(font(13, 400, mono=True))
        lcard.lay.addWidget(self.log)
        lv.addWidget(lcard)
        self.tabs.addTab(lw, "Dziennik")
        self.tabs.currentChanged.connect(self._tab_changed)
        self._tab_icons()

        self.right_stack.addWidget(pw)
        return self.right_stack

    def _tab_icons(self):
        for i, n in enumerate(("edit", "clock", "box")):
            tok = "primary" if i == self.tabs.currentIndex() else "muted"
            self.tabs.setTabIcon(i, icons.icon(n, T[tok], 18))

    def _on_theme(self):
        self._tab_icons()
        self._search_action.setIcon(icons.icon("search", T["muted"], 22))
        for lst in (self.proj_list, self.gh_list, self.files):
            lst.viewport().update()
        if self.info:
            self._show_header(self.info)

    # ============================================================ helpers
    def run_task(self, fn, *args, on_done=None, on_error=None, busy_text="", quiet=False, **kwargs):
        w = Worker(fn, *args, **kwargs)
        self.workers.add(w)
        if not quiet:
            self.busy += 1
            self.progress.setRange(0, 0)
            if busy_text:
                self.progress.setToolTip(busy_text)
            self._set_project_enabled(bool(self.current))

        def finish():
            self.workers.discard(w)
            if not quiet:
                self.busy -= 1
                if self.busy <= 0:
                    self.busy = 0
                    self.progress.setRange(0, 1)
                    self.progress.setValue(0)
                self._set_project_enabled(bool(self.current))

        def ok(res):
            finish()
            if on_done:
                on_done(res)

        def fail(msg):
            finish()
            if on_error:
                on_error(msg)
            else:
                notify(self, "Nie udało się", friendly_error(msg))

        w.signals.done.connect(ok)
        w.signals.failed.connect(fail)
        self.pool.start(w)

    def repo(self, path: str | None = None) -> Repo:
        return Repo(path or self.current, token=self.token, log=self.logbus)

    def _append_log(self, cmd: str, out: str):
        ts = time.strftime("%H:%M:%S")
        self.log.appendPlainText(f"[{ts}] $ {cmd}" + (f"\n{out}" if out else ""))

    def say(self, text: str, ms: int = 2600):
        self.toast.show_message(text, ms)

    def _set_project_enabled(self, on: bool):
        on = on and self.busy == 0
        has_remote = bool(self.info and self.info.remote_url)
        for w in (self.btn_pull, self.btn_push, self.btn_web):
            w.setEnabled(on and has_remote)
        self.btn_ignore.setEnabled(on)
        self._update_commit_buttons()

    def _checked_paths(self) -> list[str]:
        return [self.files.item(i).data(ROLE_DATA).path for i in range(self.files.count())
                if self.files.item(i).checkState() == Qt.Checked]

    def _update_commit_buttons(self, *_):
        checked = self._checked_paths()
        ok = (self.busy == 0 and bool(self.current) and bool(self.info and self.info.is_repo)
              and bool(checked) and bool(self.msg.toPlainText().strip()))
        self.btn_commit.setEnabled(ok)
        self.btn_commit_push.setEnabled(ok and bool(self.info and self.info.remote_url))
        n, total = len(checked), self.files.count()
        self.chk_all.blockSignals(True)
        self.chk_all.setChecked(total > 0 and n == total)
        self.chk_all.setEnabled(total > 0)
        self.chk_all.blockSignals(False)
        self.sel_count.setText(f"zaznaczono {n} z {total}" if total else "")

    @staticmethod
    def _open_path(path: str):
        if path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    @staticmethod
    def _reveal(path: str):
        if sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).parent)))

    @staticmethod
    def _mi(menu: QMenu, text: str, icon_name: str, slot, token: str = "primary"):
        a = menu.addAction(icons.icon(icon_name, T[token], 20), text)
        a.triggered.connect(slot)
        return a

    # ============================================================ startup / login
    def _startup(self):
        ver = git_version()
        if not ver:
            notify(self, "Brak programu git",
                   "Nie znaleziono programu git.\n\nZainstaluj Git for Windows ze strony "
                   "https://git-scm.com/download/win i uruchom aplikację ponownie.")
        else:
            self._append_log("git --version", ver)
        if self.token:
            self._load_user()
        else:
            self._update_login_ui()

    def _update_login_ui(self):
        if self.user:
            self.btn_account.setText(self.user.login)
            self.btn_account.setToolTip(f"Zalogowano: {self.user.name}")
            self.gh_stack.setCurrentIndex(0)
        else:
            self.btn_account.setText("Zaloguj do GitHuba")
            self.btn_account.setToolTip("")
            self.gh_stack.setCurrentIndex(1)

    def _load_user(self):
        gh = GitHub(self.token)

        def done(user):
            self.user = user
            self._update_login_ui()
            self.load_gh_repos()

        def fail(msg):
            self.user = None
            self._update_login_ui()
            notify(self, "Nie udało się połączyć z GitHubem", friendly_error(msg) + "\n\nZaloguj się ponownie.")

        self.run_task(gh.user, on_done=done, on_error=fail, busy_text="Łączenie z GitHubem")

    def _account_clicked(self):
        if not self.user:
            self.login()
            return
        m = QMenu(self)
        self._mi(m, "Otwórz profil na GitHubie", "share",
                 lambda: QDesktopServices.openUrl(QUrl(f"https://github.com/{self.user.login}")))
        m.addSeparator()
        self._mi(m, "Wyloguj", "close", self.logout, "danger")
        m.exec(self.btn_account.mapToGlobal(self.btn_account.rect().bottomLeft()))

    def logout(self):
        if ask(self, "Wyloguj", "Usunąć zapisany token z tego komputera?", "Wyloguj", danger=True):
            delete_token()
            self.token, self.user, self.gh_repos = None, None, []
            self._fill_gh_list()
            self._update_login_ui()
            self.say("Wylogowano")

    def login(self):
        dlg = LoginDialog(self)
        if dlg.exec() != LoginDialog.Accepted or not dlg.value():
            return
        token = dlg.value()

        def done(user):
            self.token, self.user = token, user
            if not save_token(token):
                notify(self, "Token", "Nie udało się zapisać tokenu w Menedżerze poświadczeń – "
                       "będzie działał tylko do zamknięcia aplikacji.")
            self._update_login_ui()
            self.load_gh_repos()
            self.say(f"Zalogowano jako {user.login}")

        self.run_task(GitHub(token).user, on_done=done, busy_text="Sprawdzanie tokenu")

    def load_gh_repos(self):
        if not self.token:
            return

        def done(repos):
            self.gh_repos = repos
            self._fill_gh_list()

        self.run_task(GitHub(self.token).repos, on_done=done, busy_text="Pobieranie listy repozytoriów")

    def _fill_gh_list(self, *_):
        self.gh_list.clear()
        q = self.gh_filter.text().strip().lower()
        for r in self.gh_repos:
            if q and q not in r.full_name.lower() and q not in r.description.lower():
                continue
            it = QListWidgetItem()
            it.setData(ROLE_DATA, r)
            it.setToolTip(r.html_url)
            self.gh_list.addItem(it)
        self.seg_group.button(1).setText(f"GitHub · {len(self.gh_repos)}" if self.gh_repos else "GitHub")

    def _selected_gh(self):
        it = self.gh_list.currentItem()
        return it.data(ROLE_DATA) if it else None

    def _gh_menu(self, pos, item=None):
        item = item or (self.gh_list.itemAt(pos) if pos is not None else None)
        if not item:
            return
        self.gh_list.setCurrentItem(item)
        m = QMenu(self)
        self._mi(m, "Sklonuj do nowego folderu", "download", self._gh_clone)
        self._mi(m, "Powiąż z folderem na dysku", "folder", self._gh_link)
        self._mi(m, "Otwórz na GitHubie", "share", self._gh_open)
        m.exec(self.gh_list.viewport().mapToGlobal(pos) if pos is not None else self.cursor().pos())

    def _gh_clone(self):
        r = self._selected_gh()
        self.clone_repo(r.full_name if r else "")

    def _gh_link(self):
        r = self._selected_gh()
        self.link_folder(repo=r.full_name if r else "")

    def _gh_open(self):
        r = self._selected_gh()
        if r:
            QDesktopServices.openUrl(QUrl(r.html_url))

    # ============================================================ projekty
    def reload_projects(self, select: str | None = None):
        select = select or self.current
        old_meta = {self.proj_list.item(i).data(ROLE_DATA): self.proj_list.item(i).data(ROLE_META)
                    for i in range(self.proj_list.count())}
        self.proj_list.blockSignals(True)
        self.proj_list.clear()
        for p in self.cfg.projects:
            it = QListWidgetItem()
            it.setData(ROLE_DATA, p)
            it.setData(ROLE_META, old_meta.get(p) or {})
            it.setToolTip(p)
            self.proj_list.addItem(it)
        self.proj_list.blockSignals(False)
        self.proj_stack.setCurrentIndex(0 if self.cfg.projects else 1)
        for i in range(self.proj_list.count()):
            if self.proj_list.item(i).data(ROLE_DATA) == select:
                self.proj_list.setCurrentRow(i)
                break
        else:
            if self.proj_list.count():
                self.proj_list.setCurrentRow(0)
        if not self.cfg.projects:
            self.current = ""
            self._show_info(None)
        self._refresh_project_labels()

    def _refresh_project_labels(self):
        paths = list(self.cfg.projects)

        def collect():
            res = {}
            for p in paths:
                if not Path(p).is_dir():
                    res[p] = {"token": theme.STATUS_NEUTRAL, "word": "brak folderu", "meta": ""}
                    continue
                info = Repo(p).info()
                tok, word = status_of(info)
                res[p] = {"token": tok, "word": word, "meta": info.branch}
            return res

        def done(res):
            for i in range(self.proj_list.count()):
                it = self.proj_list.item(i)
                p = it.data(ROLE_DATA)
                if p in res:
                    it.setData(ROLE_META, res[p])

        self.run_task(collect, on_done=done, quiet=True, on_error=lambda m: None)

    def _project_selected(self, item, _prev=None):
        self.current = item.data(ROLE_DATA) if item else ""
        self.msg.clear()
        self.files.clear()
        self.refresh_current(fetch=True)

    def _project_menu(self, pos, anchor=None):
        item = self.proj_list.itemAt(pos) if pos is not None else self.proj_list.currentItem()
        if not item:
            return
        p = item.data(ROLE_DATA)
        m = QMenu(self)
        self._mi(m, "Otwórz folder", "folder", lambda: self._open_path(p))
        self._mi(m, "Zmień powiązanie z GitHubem", "share", lambda: self.link_folder(folder=p))
        self._mi(m, "Utwórz dla niego repozytorium", "plus", lambda: self.create_repo(folder=p))
        m.addSeparator()
        self._mi(m, "Usuń z listy", "trash", self.remove_current_project, "danger")
        if pos is not None:
            m.exec(self.proj_list.viewport().mapToGlobal(pos))
        elif anchor is not None:
            m.exec(anchor.mapToGlobal(anchor.rect().bottomLeft()))
        else:
            m.exec(self.cursor().pos())

    def add_existing_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Wybierz folder projektu", str(Path.home()))
        if not d:
            return
        d = os.path.normpath(d)
        if not Repo(d).is_repo():
            ans = choose(self, "Dodaj folder", "Ten folder nie jest jeszcze repozytorium git.\n\n"
                         "Powiązać go od razu z repozytorium na GitHubie?",
                         ["Powiąż z GitHubem", "Tylko dodaj do listy"])
            if ans == 0:
                self.link_folder(folder=d)
                return
            if ans < 0:
                return
            try:
                Repo(d, log=self.logbus).init()
            except Exception as e:  # noqa: BLE001
                notify(self, "Nie udało się", str(e))
                return
        self.cfg.add_project(d)
        self.reload_projects(select=d)
        self.say("Dodano projekt")

    def remove_current_project(self):
        it = self.proj_list.currentItem()
        if not it:
            return
        p = it.data(ROLE_DATA)
        if ask(self, "Usuń z listy", f"Usunąć „{Path(p).name}” z listy?\n\n"
               "Pliki na dysku i repozytorium na GitHubie pozostaną bez zmian.", "Usuń z listy", danger=True):
            self.cfg.remove_project(p)
            self.current = ""
            self.info = None
            self.reload_projects()
            self.say("Projekt usunięty z listy")

    # ============================================================ akcje GitHub
    def _require_login(self) -> bool:
        if self.user and self.token:
            return True
        self.login()
        return bool(self.user)

    def link_folder(self, folder: str = "", repo: str = ""):
        if not self._require_login():
            return
        dlg = LinkDialog(self.gh_repos, self, folder=folder or "", repo=repo)
        if dlg.exec() != LinkDialog.Accepted:
            return
        path, url, branch = dlg.values()
        r = self.repo(path)
        old = r.remote_url() if r.is_repo() else ""
        if old and old != url:
            if not ask(self, "Zmiana powiązania", f"Folder jest już powiązany z:\n{old}\n\nZmienić na:\n{url}?",
                       "Zmień powiązanie"):
                return

        def done(note):
            self.cfg.add_project(path)
            self.seg_group.button(0).click()
            self.reload_projects(select=path)
            self._append_log("powiązanie folderu", note)
            self.say("Powiązano z GitHubem. " + note.splitlines()[-1], 4500)

        self.run_task(r.link_to_remote, url, branch, on_done=done, busy_text="Wiązanie folderu z GitHubem")

    def create_repo(self, folder: str = ""):
        if not self._require_login():
            return
        if not folder and self.current and self.info and self.info.is_repo and not self.info.remote_url:
            folder = self.current
        dlg = CreateRepoDialog(self, folder=folder)
        if dlg.exec() != CreateRepoDialog.Accepted:
            return
        name, desc, private, path, readme = dlg.values()
        gh = GitHub(self.token)

        def work():
            repo = gh.create_repo(name, desc, private, auto_init=readme)
            note = ""
            if path:
                note = self.repo(path).link_to_remote(repo.clone_url, repo.default_branch)
            return repo, note

        def done(res):
            repo, note = res
            self.gh_repos.insert(0, repo)
            self._fill_gh_list()
            if path:
                self._append_log("powiązanie folderu", note)
                self.cfg.add_project(path)
                self.seg_group.button(0).click()
                self.reload_projects(select=path)
                self.say(f"Utworzono {repo.full_name}. Zaznacz pliki, opisz zmiany i wyślij.", 4500)
            else:
                self.say(f"Utworzono {repo.full_name}")

        self.run_task(work, on_done=done, busy_text="Tworzenie repozytorium")

    def clone_repo(self, repo: str = ""):
        if not self._require_login():
            return
        dlg = CloneDialog(self.gh_repos, self.cfg.clone_dir, self, repo=repo)
        if dlg.exec() != CloneDialog.Accepted:
            return
        url, dest, parent = dlg.values()
        self.cfg.clone_dir = parent

        def done(_):
            self.cfg.add_project(dest)
            self.seg_group.button(0).click()
            self.reload_projects(select=dest)
            self.say(f"Sklonowano do {dest}", 3500)

        self.run_task(clone, url, dest, self.token, self.logbus, on_done=done, busy_text="Klonowanie")

    # ============================================================ bieżący projekt
    def refresh_all(self):
        self.reload_projects()
        self.refresh_current(fetch=True, force_fetch=True)
        if self.user:
            self.load_gh_repos()

    def refresh_current(self, fetch: bool = False, force_fetch: bool = False):
        path = self.current
        if not path:
            self._show_info(None)
            return
        do_fetch = False
        if fetch and self.token:
            last = self.last_fetch.get(path, 0)
            do_fetch = force_fetch or (time.time() - last > 60)

        def work():
            r = self.repo(path)
            if do_fetch and r.is_repo() and r.remote_url():
                try:
                    r.fetch()
                except Exception:  # noqa: BLE001 – brak sieci nie blokuje widoku
                    pass
            return r.info()

        def done(info):
            if do_fetch:
                self.last_fetch[path] = time.time()
            if path == self.current:
                self._show_info(info)

        self.run_task(work, on_done=done, quiet=not do_fetch, busy_text="Sprawdzanie zmian na GitHubie")

    def _show_header(self, info: RepoInfo):
        p = info.path
        exists = Path(p).is_dir()
        self.h_name.setText(Path(p).name)
        self.h_path.setText(p)
        tok, word = status_of(info, exists)
        self.h_badge.set(tok, word)
        web = self._web_url(info.remote_url)
        if web:
            self.h_remote.setText(f"<a style='color:{T['primary']}; text-decoration:none' href='{web}'>"
                                  f"{web.replace('https://', '')}</a>")
        elif info.remote_url:
            self.h_remote.setText(info.remote_url)
        else:
            self.h_remote.setText(f"<span style='color:{T['muted']}'>Bez GitHuba – użyj „Powiąż folder”</span>")
        if not exists:
            self.h_branch.setText(f"<span style='color:{T['danger']}'>Folder nie istnieje</span>")
        elif not info.is_repo:
            self.h_branch.setText(f"<span style='color:{T['muted']}'>Folder nie jest repozytorium git</span>")
        else:
            sync = ""
            if info.upstream:
                bits = [f"{info.ahead} do wysłania" if info.ahead else "",
                        f"{info.behind} do pobrania" if info.behind else ""]
                sync = " · ".join(b for b in bits if b) or "zgodna z GitHubem"
            elif info.remote_url:
                sync = (f"jeszcze nie na GitHubie · {plural_commit(info.ahead)} do wysłania"
                        if info.has_commits else "brak commitów")
            self.h_branch.setText(f"Gałąź <b>{info.branch or '?'}</b>"
                                  + (f" <span style='color:{T['muted']}'>· {sync}</span>" if sync else ""))
        self.btn_pull.setText(f"Pobierz · {info.behind}" if info.behind else "Pobierz")
        self.btn_push.setText(f"Wyślij · {info.ahead}" if info.ahead else "Wyślij")
        # Gdy są commity do wysłania, „Wyślij” staje się główną akcją.
        self._set_kind(self.btn_push, "upload", "primary" if info.ahead else "ghost")
        self._set_kind(self.btn_pull, "download", "primary" if info.behind and not info.ahead else "ghost")

    @staticmethod
    def _set_kind(b, icon_name: str, kind: str):
        name = "primary" if kind == "primary" else ""
        if b.objectName() != name:
            b.setObjectName(name)
            b.style().unpolish(b)
            b.style().polish(b)
        b.setIcon(icons.icon(icon_name, T["on-primary" if kind == "primary" else "primary"], 20,
                             disabled_color=T["muted"]))

    def _show_info(self, info: RepoInfo | None):
        self.info = info
        prev_sel = set(self._checked_paths())
        had_items = self.files.count() > 0
        cur_item = self.files.currentItem()
        cur_path = cur_item.data(ROLE_DATA).path if cur_item else None
        self.files.blockSignals(True)
        self.files.clear()
        self.merge_bar.setVisible(bool(info and info.merging))
        if not info:
            self.files.blockSignals(False)
            self.right_stack.setCurrentIndex(0)
            self._set_project_enabled(False)
            self.hist.setRowCount(0)
            return
        self.right_stack.setCurrentIndex(1)
        self._show_header(info)
        for c in info.changes:
            it = QListWidgetItem()
            it.setData(ROLE_DATA, c)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            checked = (c.path in prev_sel) if had_items else True
            it.setCheckState(Qt.Checked if checked or info.merging else Qt.Unchecked)
            it.setToolTip(str(Path(info.path) / c.path))
            self.files.addItem(it)
            if c.path == cur_path:
                self.files.setCurrentItem(it)
        if not self.files.currentItem() and self.files.count():
            self.files.setCurrentRow(0)
        self.files.blockSignals(False)
        if self.files.currentItem():
            self._file_selected(self.files.currentItem())
        else:
            self.diff_title.setText("Podgląd")
            self.diff_badge.set("muted", "")
            self.diff_stack.setCurrentIndex(1)
            self.empty_push.setVisible(bool(info.ahead and info.remote_url))
            self.empty_pull.setVisible(bool(info.behind and not info.ahead))
            if not info.is_repo:
                self.diff_empty.set_text("To nie jest repozytorium",
                                         "Użyj „Powiąż folder”, żeby połączyć go z GitHubem.", "box")
            elif info.ahead and info.remote_url:
                self.diff_empty.set_text("Czeka na wysłanie",
                                         f"Do wysłania: {plural_commit(info.ahead)}. "
                                         "Zmiany są zatwierdzone, ale nie ma ich jeszcze na GitHubie.", "upload")
            elif info.behind:
                self.diff_empty.set_text("Na GitHubie są nowe zmiany",
                                         f"Do pobrania: {plural_commit(info.behind)}.", "download")
            elif info.has_commits:
                self.diff_empty.set_text("Brak zmian", "Wszystko jest zatwierdzone.", "box")
            else:
                self.diff_empty.set_text("Folder jest pusty", "Dodaj pliki projektu – pojawią się tutaj.", "box")
        self.tabs.setTabText(0, f"Zmiany · {len(info.changes)}" if info.changes else "Zmiany")
        self._set_project_enabled(True)
        if self.tabs.currentIndex() == 1:
            self.load_history()
        self._refresh_project_labels()

    @staticmethod
    def _web_url(remote: str) -> str:
        if not remote:
            return ""
        u = remote
        if u.startswith("git@github.com:"):
            u = "https://github.com/" + u.split(":", 1)[1]
        if u.endswith(".git"):
            u = u[:-4]
        return u if u.startswith("http") else ""

    def _open_current_web(self):
        u = self._web_url(self.info.remote_url if self.info else "")
        if u:
            QDesktopServices.openUrl(QUrl(u))

    def _toggle_all(self, checked: bool):
        self.files.blockSignals(True)
        for i in range(self.files.count()):
            self.files.item(i).setCheckState(Qt.Checked if checked else Qt.Unchecked)
        self.files.blockSignals(False)
        self.files.viewport().update()
        self._update_commit_buttons()

    def _file_selected(self, item, _prev=None):
        if not item or not self.current:
            return
        change = item.data(ROLE_DATA)
        path = self.current
        self.diff_title.setText(change.path.replace("\\", "/"))
        self.diff_badge.set(KIND_TOKENS.get(change.kind, "muted"), change.kind)
        self.diff_stack.setCurrentIndex(0)

        def done(txt):
            if self.current == path:
                self.diff.show_text(txt)

        self.run_task(self.repo(path).file_diff, change, on_done=done, quiet=True,
                      on_error=lambda m: self.diff.show_text(m))

    def _file_menu(self, pos):
        item = self.files.itemAt(pos)
        if not item:
            return
        c = item.data(ROLE_DATA)
        full = str(Path(self.current) / c.path)
        m = QMenu(self)
        self._mi(m, "Otwórz plik", "edit", lambda: self._open_path(full))
        self._mi(m, "Pokaż w folderze", "folder", lambda: self._reveal(full))
        m.addSeparator()
        self._mi(m, "Ignoruj ten plik", "close", lambda: self._ignore(c.path), "muted")
        ext = Path(c.path).suffix
        if ext:
            self._mi(m, f"Ignoruj wszystkie pliki *{ext}", "close", lambda: self._ignore(f"*{ext}"), "muted")
        parent = str(Path(c.path).parent).replace("\\", "/")
        if parent and parent != ".":
            self._mi(m, f"Ignoruj folder {parent}/", "close", lambda: self._ignore(parent + "/"), "muted")
        m.addSeparator()
        self._mi(m, "Usuń nowy plik" if c.kind == "nowy" else "Cofnij zmiany w pliku", "trash",
                 lambda: self._discard(c), "danger")
        m.exec(self.files.viewport().mapToGlobal(pos))

    def _ignore(self, pattern: str):
        self.repo().ignore(pattern.replace("\\", "/"))
        self.say(f"Dodano do .gitignore: {pattern}")
        self.refresh_current()

    def _discard(self, c):
        if c.kind == "nowy":
            text, ok = f"{c.path}\n\nPlik zostanie usunięty z dysku. Tej operacji nie da się cofnąć.", "Usuń plik"
        else:
            text, ok = (f"{c.path}\n\nPlik wróci do wersji z ostatniego commita. "
                        "Tej operacji nie da się cofnąć.", "Cofnij zmiany")
        if not ask(self, "Cofnij zmiany", text, ok, danger=True):
            return

        def done(_):
            self.say("Cofnięto zmiany")
            self.refresh_current()

        self.run_task(self.repo().discard, c, on_done=done)

    def edit_gitignore(self):
        if not self.current:
            return
        dlg = GitignoreDialog(self.current, self.run_task, GitHub(self.token), self)
        if dlg.exec() == GitignoreDialog.Accepted:
            self.say("Zaktualizowano .gitignore")
            self.refresh_current()

    def commit(self, push: bool):
        paths = self._checked_paths()
        msg = self.msg.toPlainText().strip()
        if not paths or not msg:
            return
        r = self.repo()
        big = r.large_files(paths)
        if big:
            lst = "\n".join(f"• {p} ({s / 1024 / 1024:.0f} MB)" for p, s in big)
            if ask(self, "Za duże pliki", f"GitHub nie przyjmie plików większych niż "
                   f"{GITHUB_LIMIT_BYTES // 1024 // 1024} MB:\n\n{lst}\n\nDodać je do .gitignore i pominąć?",
                   "Dodaj do .gitignore"):
                for p, _ in big:
                    r.ignore(p.replace("\\", "/"))
            self.refresh_current()
            return
        name = self.user.name if self.user else ""
        email = self.user.commit_email if self.user else ""

        def work():
            r.commit(paths, msg, name, email)
            if push:
                r.push()
                return "Zatwierdzono i wysłano na GitHuba"
            return "Zatwierdzono"

        def done(text):
            self.msg.clear()
            self.say(text)
            self.last_fetch[self.current] = time.time()
            self.refresh_current()

        def fail(m):
            self.refresh_current()
            notify(self, "Nie udało się wysłać" if push else "Nie udało się zatwierdzić", friendly_error(m))

        self.run_task(work, on_done=done, on_error=fail, busy_text="Zatwierdzanie")

    def push(self):
        if not self.token and not ask(self, "Wyślij", "Nie jesteś zalogowany – git spróbuje użyć poświadczeń "
                                      "zapisanych w systemie.", "Wyślij"):
            return

        def done(_):
            self.say("Wysłano na GitHuba")
            self.refresh_current()

        self.run_task(self.repo().push, on_done=done, busy_text="Wysyłanie")

    def pull(self):
        def done(text):
            self.say("Pobrano zmiany z GitHuba")
            self._append_log("wynik pobierania", text)
            self.last_fetch[self.current] = time.time()
            self.refresh_current()

        def fail(m):
            self.refresh_current()
            notify(self, "Nie udało się pobrać zmian", friendly_error(m))

        self.run_task(self.repo().pull, on_done=done, on_error=fail, busy_text="Pobieranie zmian")

    def abort_merge(self):
        if not ask(self, "Przerwij scalanie", "Przywrócić stan sprzed pobrania zmian?", "Przerwij scalanie",
                   danger=True):
            return

        def done(_):
            self.say("Przerwano scalanie")
            self.refresh_current()

        self.run_task(self.repo().abort_merge, on_done=done)

    # ============================================================ historia
    def _tab_changed(self, idx: int):
        self._tab_icons()
        if idx == 1:
            self.load_history()

    def load_history(self):
        if not self.current or not (self.info and self.info.is_repo):
            self.hist.setRowCount(0)
            return
        path = self.current

        def done(commits):
            if path != self.current:
                return
            self.hist.setRowCount(len(commits))
            mono = font(13, 400, mono=True)
            for row, c in enumerate(commits):
                for col, val in enumerate((c.short, c.date, c.author, c.subject)):
                    it = QTableWidgetItem(val)
                    it.setData(Qt.UserRole, c.sha)
                    if col == 0:
                        it.setFont(mono)
                        it.setForeground(T.q("primary"))
                    elif col in (1, 2):
                        it.setForeground(T.q("muted"))
                    self.hist.setItem(row, col, it)
            self.hist_diff.clear()

        self.run_task(self.repo(path).log_commits, on_done=done, quiet=True)

    def _commit_selected(self, row, *_):
        it = self.hist.item(row, 0)
        if not it:
            return
        self.run_task(self.repo().show_commit, it.data(Qt.UserRole), on_done=self.hist_diff.show_text, quiet=True)

    # ============================================================ zdarzenia
    def changeEvent(self, e):
        # Po powrocie do okna (np. z edytora) odśwież listę zmian.
        if e.type() == QEvent.ActivationChange and self.isActiveWindow() and self.current and self.busy == 0:
            self.refresh_current()
        super().changeEvent(e)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.toast.isVisible():
            self.toast._place()

    def closeEvent(self, e):
        if self.busy and not ask(self, "EasyGit", "Trwa operacja. Zamknąć mimo to?", "Zamknij"):
            e.ignore()
            return
        super().closeEvent(e)


def main():
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("EasyGit.App")
        except Exception:  # noqa: BLE001
            pass
    app = QApplication(sys.argv)
    app.setApplicationName("EasyGit")
    app.setApplicationVersion(__version__)
    theme.apply(app, os.environ.get("EASYGIT_THEME") or None)
    theme.follow_system(app)
    app.setWindowIcon(app_icon())
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
