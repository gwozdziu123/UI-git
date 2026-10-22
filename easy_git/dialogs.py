"""Okna dialogowe w stylu arkusza (sheet): tytuł, pola z etykietą nad polem, stopka z akcją główną."""
from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QTextCursor
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFileDialog, QFrame, QHBoxLayout, QLineEdit, QListWidget,
                               QListWidgetItem, QPlainTextEdit, QSplitter, QVBoxLayout, QWidget)

from .gitignore_templates import TEMPLATES
from .git_ops import Repo
from .theme import T, font, on_change
from .widgets import (Banner, Card, GitignoreHighlighter, ask, button, field, label, notify, section_label,
                      separator)

TOKEN_URL = "https://github.com/settings/tokens/new?scopes=repo&description=UI-git"


def slugify_repo_name(name: str) -> str:
    name = name.replace("ł", "l").replace("Ł", "L")
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-.")
    return name or "nowe-repozytorium"


def folder_input(parent: QWidget, edit: QLineEdit, title: str) -> QWidget:
    w = QWidget(parent)
    h = QHBoxLayout(w)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(10)
    h.addWidget(edit, 1)
    b = button("Wybierz", "ghost", "folder")
    b.setMinimumHeight(44)

    def pick():
        d = QFileDialog.getExistingDirectory(parent, title, edit.text() or str(Path.home()))
        if d:
            edit.setText(os.path.normpath(d))
    b.clicked.connect(pick)
    h.addWidget(b)
    return w


class SheetDialog(QDialog):
    """Szkielet: tytuł 19/700, treść z odstępem 14 px między polami, stopka: Anuluj + akcja główna."""

    def __init__(self, title: str, ok_text: str, parent=None, width: int = 620):
        super().__init__(parent)
        self.setObjectName("sheet")
        self.setWindowTitle(title)
        self.setMinimumWidth(width)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        head = QVBoxLayout()
        head.setContentsMargins(20, 18, 20, 4)
        head.addWidget(label(title, "sheetTitle"))
        root.addLayout(head)
        self.body = QVBoxLayout()
        self.body.setContentsMargins(20, 10, 20, 18)
        self.body.setSpacing(14)
        root.addLayout(self.body, 1)
        root.addWidget(separator())
        foot = QHBoxLayout()
        foot.setContentsMargins(20, 12, 20, 16)
        foot.setSpacing(10)
        self.cancel_btn = button("Anuluj", "ghost", tall=True)
        self.cancel_btn.setMinimumHeight(48)
        self.cancel_btn.setMinimumWidth(120)
        self.cancel_btn.clicked.connect(self.reject)
        self.ok_btn = button(ok_text, "primary", tall=True)
        self.ok_btn.setDefault(True)
        self.ok_btn.clicked.connect(self._ok)
        foot.addWidget(self.cancel_btn)
        foot.addWidget(self.ok_btn, 1)
        root.addLayout(foot)

    def _ok(self):
        self.accept()


class LoginDialog(SheetDialog):
    def __init__(self, parent=None):
        super().__init__("Logowanie do GitHuba", "Zaloguj", parent, 560)
        self.body.addWidget(label(
            "Aplikacja łączy się z GitHubem tokenem dostępu (Personal Access Token). "
            "Token zostanie zapisany w Menedżerze poświadczeń Windows, nie w pliku.", "", wrap=True))
        steps = label("1. Utwórz token – GitHub otworzy się z zaznaczonym uprawnieniem repo.\n"
                      "2. Ustaw datę ważności, kliknij Generate token i skopiuj token.\n"
                      "3. Wklej go poniżej.", "secondary", wrap=True)
        self.body.addWidget(steps)
        b = button("Utwórz token na GitHubie", "ghost", "share")
        b.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(TOKEN_URL)))
        self.body.addWidget(b, 0, Qt.AlignLeft)
        self.token = QLineEdit()
        self.token.setEchoMode(QLineEdit.Password)
        self.token.setPlaceholderText("ghp_… lub github_pat_…")
        self.body.addWidget(field("Token", self.token))

    def _ok(self):
        if not self.value():
            self.token.setProperty("err", True)
            self.token.style().polish(self.token)
            return
        self.accept()

    def value(self) -> str:
        return self.token.text().strip()


class RepoPicker(QComboBox):
    """Edytowalna lista repozytoriów z GitHuba (można też wkleić adres URL)."""

    def __init__(self, repos, parent=None, preselect: str = ""):
        super().__init__(parent)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.NoInsert)
        self.repos = repos
        for r in repos:
            self.addItem(r.full_name, r)
        self.lineEdit().setPlaceholderText("wybierz z listy lub wklej https://github.com/użytkownik/repo.git")
        idx = next((i for i, r in enumerate(repos) if r.full_name == preselect), -1)
        self.setCurrentIndex(idx)
        if idx < 0:
            self.setEditText("")

    def selected(self):
        """Zwraca (url, default_branch, nazwa)."""
        text = self.currentText().strip()
        for r in self.repos:
            if text in (r.full_name, r.clone_url, r.html_url):
                return r.clone_url, r.default_branch, r.name
        if not text:
            return "", "main", ""
        url = text
        if re.fullmatch(r"[\w.-]+/[\w.-]+", text):
            url = f"https://github.com/{text}.git"
        name = url.rstrip("/").split("/")[-1].removesuffix(".git")
        return url, "main", name


class LinkDialog(SheetDialog):
    def __init__(self, repos, parent=None, folder: str = "", repo: str = ""):
        super().__init__("Powiąż folder z repozytorium", "Powiąż", parent)
        self.body.addWidget(label("Jeśli folder nie jest jeszcze repozytorium git, zostanie przygotowany. "
                                  "Twoje pliki nie zostaną nadpisane.", "secondary", wrap=True))
        self.folder = QLineEdit(folder)
        self.body.addWidget(field("Folder na dysku", folder_input(self, self.folder, "Wybierz folder projektu")))
        self.picker = RepoPicker(repos, self, repo)
        self.body.addWidget(field("Repozytorium na GitHubie", self.picker))

    def _ok(self):
        if not Path(self.folder.text()).is_dir():
            notify(self, "Powiąż folder", "Wybierz istniejący folder.")
            return
        if not self.picker.selected()[0]:
            notify(self, "Powiąż folder", "Wybierz repozytorium.")
            return
        self.accept()

    def values(self):
        url, branch, _ = self.picker.selected()
        return os.path.normpath(self.folder.text()), url, branch


class CloneDialog(SheetDialog):
    def __init__(self, repos, clone_dir: str, parent=None, repo: str = ""):
        super().__init__("Sklonuj repozytorium", "Sklonuj", parent)
        self.picker = RepoPicker(repos, self, repo)
        self.body.addWidget(field("Repozytorium", self.picker))
        self.parent_dir = QLineEdit(clone_dir)
        self.body.addWidget(field("Zapisz w folderze", folder_input(self, self.parent_dir, "Folder docelowy")))
        self.name = QLineEdit()
        self.body.addWidget(field("Nazwa nowego folderu", self.name))
        self.picker.currentTextChanged.connect(self._sync_name)
        self._sync_name()

    def _sync_name(self, *_):
        self.name.setText(self.picker.selected()[2])

    def _ok(self):
        url = self.picker.selected()[0]
        if not url or not self.name.text().strip():
            notify(self, "Klonowanie", "Wybierz repozytorium i nazwę folderu.")
            return
        dest = Path(self.parent_dir.text()) / self.name.text().strip()
        if dest.exists() and any(dest.iterdir()):
            notify(self, "Klonowanie", f"Folder {dest} już istnieje i nie jest pusty.\n"
                   "Użyj „Powiąż folder”, żeby podłączyć istniejący folder.")
            return
        self.accept()

    def values(self):
        return (self.picker.selected()[0],
                os.path.normpath(str(Path(self.parent_dir.text()) / self.name.text().strip())),
                self.parent_dir.text())


class CreateRepoDialog(SheetDialog):
    def __init__(self, parent=None, folder: str = ""):
        super().__init__("Nowe repozytorium", "Utwórz repozytorium", parent)
        self.name = QLineEdit(slugify_repo_name(Path(folder).name) if folder else "")
        self.body.addWidget(field("Nazwa", self.name, "Dozwolone: litery bez polskich znaków, cyfry oraz . - _"))
        self.desc = QLineEdit()
        self.body.addWidget(field("Opis (opcjonalnie)", self.desc))
        self.private = QCheckBox("Prywatne – widoczne tylko dla Ciebie")
        self.private.setChecked(True)
        self.body.addWidget(self.private)
        self.folder = QLineEdit(folder)
        self.folder.setPlaceholderText("opcjonalnie – folder, który od razu zostanie powiązany")
        self.body.addWidget(field("Powiąż z folderem", folder_input(self, self.folder, "Folder projektu")))
        self.readme = QCheckBox("Dodaj plik README (tylko bez powiązanego folderu)")
        self.body.addWidget(self.readme)
        self.folder.textChanged.connect(self._sync)
        self._sync()

    def _sync(self, *_):
        has_folder = bool(self.folder.text().strip())
        self.readme.setEnabled(not has_folder)
        if has_folder:
            self.readme.setChecked(False)
        if has_folder and not self.name.text().strip():
            self.name.setText(slugify_repo_name(Path(self.folder.text()).name))

    def _ok(self):
        n = self.name.text().strip()
        bad = not n or slugify_repo_name(n) != n
        self.name.setProperty("err", bad)
        self.name.style().polish(self.name)
        if bad:
            if n:
                self.name.setText(slugify_repo_name(n))
            return
        fo = self.folder.text().strip()
        if fo and not Path(fo).is_dir():
            notify(self, "Nowe repozytorium", "Wybrany folder nie istnieje.")
            return
        self.accept()

    def values(self):
        fo = self.folder.text().strip()
        return (self.name.text().strip(), self.desc.text().strip(), self.private.isChecked(),
                os.path.normpath(fo) if fo else "", self.readme.isChecked())


class GitignoreDialog(SheetDialog):
    """Edytor pliku .gitignore: własne reguły, gotowe szablony i sprawdzenie, które pliki zostaną pominięte."""

    def __init__(self, folder: str, run_task, github, parent=None, log=None):
        super().__init__(".gitignore", "Zapisz", parent, 980)
        self.resize(1080, 800)
        self.folder, self.run_task, self.github = folder, run_task, github
        self.repo = Repo(folder, log=log)
        self.is_repo = self.repo.is_repo()
        self.remote_cache: dict[str, str] = {}
        self.result_msg = "Zapisano .gitignore"
        self.tracked: list[str] = []
        self.path = Path(folder) / ".gitignore"
        self.original = self.path.read_text(encoding="utf-8", errors="replace") if self.path.exists() else ""

        self.body.addWidget(label("Wpisz reguły bezpośrednio albo dodaj gotowy szablon. Pliki pasujące do reguł "
                                  "nie będą wysyłane na GitHuba.", "secondary", wrap=True))
        sp = QSplitter(self)
        sp.setHandleWidth(12)
        sp.setChildrenCollapsible(False)

        # --- szablony
        left = Card(padding=(0, 0, 0, 0), spacing=0)
        left.setMinimumWidth(250)
        left.lay.addWidget(_head(section_label("Szablony")))
        left.lay.addWidget(separator())
        self.list = QListWidget()
        self.list.setObjectName("plain")
        self.list.setSpacing(1)
        for name in TEMPLATES:
            self._add_item(name, ("local", name))
        self.list.itemDoubleClicked.connect(self._insert_selected)
        self.list.currentItemChanged.connect(self._sync_tpl_buttons)
        wrap = QWidget()
        wl = QVBoxLayout(wrap)
        wl.setContentsMargins(6, 6, 6, 6)
        wl.addWidget(self.list)
        left.lay.addWidget(wrap, 1)
        left.lay.addWidget(separator())
        lf = QVBoxLayout()
        lf.setContentsMargins(8, 6, 8, 8)
        lf.setSpacing(2)
        self.insert_btn = button("Dodaj do pliku", "add", "plus")
        self.insert_btn.clicked.connect(self._insert_selected)
        lf.addWidget(self.insert_btn, 0, Qt.AlignLeft)
        self.load_btn = button("Więcej z GitHuba", "add", "download")
        self.load_btn.clicked.connect(self._load_remote)
        lf.addWidget(self.load_btn, 0, Qt.AlignLeft)
        left.lay.addLayout(lf)
        sp.addWidget(left)

        # --- edytor
        right = Card(padding=(0, 0, 0, 0), spacing=0)
        self.state = label("", "caption")
        right.lay.addWidget(_head(section_label("Plik .gitignore"), self.state))
        right.lay.addWidget(separator())
        self.editor = QPlainTextEdit()
        self.editor.setFont(font(14, 400, mono=True))
        self.editor.setFrameShape(QFrame.NoFrame)
        self.editor.setPlaceholderText("# Przykład\n*.bak\nLogs/\n!Logs/wazny.txt")
        self.editor.setPlainText(self.original)
        self.editor.setTabChangesFocus(True)
        self.editor.setMinimumHeight(240)
        self._hl = GitignoreHighlighter(self.editor.document())
        on_change(self._recolor)
        self.editor.textChanged.connect(self._on_text)
        ew = QWidget()
        el = QVBoxLayout(ew)
        el.setContentsMargins(8, 6, 8, 6)
        el.addWidget(self.editor)
        right.lay.addWidget(ew, 1)
        right.lay.addWidget(separator())

        qa = QHBoxLayout()
        qa.setContentsMargins(12, 10, 12, 4)
        qa.setSpacing(8)
        self.quick = QLineEdit()
        self.quick.setPlaceholderText("Dodaj regułę, np. *.bak albo Logs/")
        self.quick.returnPressed.connect(self._quick_add)
        qa.addWidget(self.quick, 1)
        b = button("Dodaj", "ghost", "plus")
        b.setMinimumHeight(44)
        b.clicked.connect(self._quick_add)
        qa.addWidget(b)
        right.lay.addLayout(qa)
        hint = label("*.log – pliki z rozszerzeniem  ·  Logs/ – cały folder  ·  !wzór – wyjątek  ·  # komentarz",
                     "hint", wrap=True)
        hint.setContentsMargins(12, 0, 12, 10)
        right.lay.addWidget(hint)

        if self.is_repo:
            right.lay.addWidget(separator())
            ck = QHBoxLayout()
            ck.setContentsMargins(8, 6, 12, 6)
            self.check_btn = button("Sprawdź, co zostanie pominięte", "add", "search")
            self.check_btn.clicked.connect(self._check)
            ck.addWidget(self.check_btn)
            self.check_info = label("", "caption")
            ck.addWidget(self.check_info, 1)
            right.lay.addLayout(ck)
            self.results = QListWidget()
            self.results.setObjectName("plain")
            self.results.setMaximumHeight(104)
            self.results.hide()
            rw = QWidget()
            rl = QVBoxLayout(rw)
            rl.setContentsMargins(8, 0, 8, 8)
            rl.setSpacing(8)
            rl.addWidget(self.results)
            self.tracked_bar = Banner("")
            self.untrack_btn = button("Zapisz i wyjmij z repozytorium", "ghost")
            self.untrack_btn.clicked.connect(self._save_untrack)
            self.tracked_bar.actions.addWidget(self.untrack_btn)
            self.tracked_bar.hide()
            rl.addWidget(self.tracked_bar)
            right.lay.addWidget(rw)
        sp.addWidget(right)
        sp.setSizes([280, 740])
        sp.setStretchFactor(1, 1)
        self.body.addWidget(sp, 1)
        self._on_text()
        self.list.setCurrentRow(0)

    # ---------------------------------------------------------------- szablony
    def _add_item(self, text, data):
        it = QListWidgetItem(text)
        it.setData(Qt.UserRole, data)
        it.setSizeHint(QSize(0, 38))
        self.list.addItem(it)

    @staticmethod
    def _header(name: str) -> str:
        return f"# ===== {name} ====="

    def _sync_tpl_buttons(self, *_):
        it = self.list.currentItem()
        present = bool(it and self._header(it.data(Qt.UserRole)[1]) in self.editor.toPlainText())
        self.insert_btn.setEnabled(bool(it) and not present)
        self.insert_btn.setText("Już jest w pliku" if present else "Dodaj do pliku")

    def _mark_templates(self):
        text = self.editor.toPlainText()
        muted = T.q("muted")
        for i in range(self.list.count()):
            it = self.list.item(i)
            kind, name = it.data(Qt.UserRole)
            base = name if kind == "local" else f"GitHub: {name}"
            present = self._header(name) in text
            it.setText(f"{base}  · w pliku" if present else base)
            it.setForeground(muted if present else T.q("text"))
        self._sync_tpl_buttons()

    def _load_remote(self):
        self.load_btn.setEnabled(False)
        self.load_btn.setText("Pobieranie…")

        def done(names):
            self.load_btn.setText(f"Pobrano {len(names)} szablonów")
            for n in names:
                self._add_item(f"GitHub: {n}", ("remote", n))
            self._mark_templates()

        def fail(msg):
            self.load_btn.setEnabled(True)
            self.load_btn.setText("Więcej z GitHuba")
            notify(self, ".gitignore", "Nie udało się pobrać szablonów.\n\n" + msg)

        self.run_task(self.github.gitignore_templates, on_done=done, on_error=fail, quiet=True)

    def _text_for(self, item, cb):
        kind, name = item.data(Qt.UserRole)
        if kind == "local":
            cb(TEMPLATES[name])
        elif name in self.remote_cache:
            cb(self.remote_cache[name])
        else:
            def done(txt):
                self.remote_cache[name] = txt
                cb(txt)
            self.run_task(self.github.gitignore_template, name, on_done=done, quiet=True)

    def _insert_selected(self, *_):
        it = self.list.currentItem()
        if not it:
            return
        name = it.data(Qt.UserRole)[1]
        if self._header(name) in self.editor.toPlainText():
            return
        self._text_for(it, lambda txt: self._append(f"{self._header(name)}\n{txt.strip()}", block=True))

    # ---------------------------------------------------------------- edycja
    def _append(self, text: str, block: bool = False):
        cur = self.editor.toPlainText().rstrip("\n")
        sep = ("\n\n" if block else "\n") if cur else ""
        self.editor.setPlainText(cur + sep + text + "\n")
        c = self.editor.textCursor()
        c.movePosition(QTextCursor.End)
        self.editor.setTextCursor(c)
        self.editor.ensureCursorVisible()

    def _quick_add(self):
        rule = self.quick.text().strip().replace("\\", "/")
        if not rule:
            return
        lines = [ln.strip() for ln in self.editor.toPlainText().splitlines()]
        if rule not in lines:
            self._append(rule)
        self.quick.clear()

    def _on_text(self):
        dirty = self.editor.toPlainText() != self.original
        if dirty:
            self.state.setText(f"<span style='color:{T['warn']}'>niezapisane zmiany</span>")
        elif not self.path.exists():
            self.state.setText("nowy plik")
        else:
            n = sum(1 for ln in self.original.splitlines() if ln.strip() and not ln.strip().startswith("#"))
            self.state.setText(f"{n} reguł" if n != 1 else "1 reguła")
        self._mark_templates()

    def _recolor(self):
        self._hl.update_colors()
        self._hl.rehighlight()

    # ---------------------------------------------------------------- sprawdzanie
    def _check(self):
        self.check_btn.setEnabled(False)
        self.check_info.setText("Sprawdzanie…")

        def done(res):
            skipped, tracked = res
            # Pokaż najgłębsze wpisy (git zgłasza też folder nadrzędny, gdy wszystko w nim jest pomijane).
            skipped = [x for x in skipped if not any(o != x and o.startswith(x) for o in skipped)]
            self.check_btn.setEnabled(True)
            self.tracked = tracked
            self.results.clear()
            for x in skipped[:500]:
                self.results.addItem(QListWidgetItem(x))
            more = " (pokazano 500)" if len(skipped) > 500 else ""
            self.check_info.setText(f"Pominięte: {len(skipped)}{more}" if skipped
                                    else "Żaden nowy plik nie pasuje do reguł.")
            self.results.setVisible(bool(skipped))
            if tracked:
                names = ", ".join(tracked[:3]) + (f" i {len(tracked) - 3} innych" if len(tracked) > 3 else "")
                n = len(tracked)
                if n == 1:
                    lead = "<b>1 plik</b> pasujący do reguł jest już"
                elif n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
                    lead = f"<b>{n} pliki</b> pasujące do reguł są już"
                else:
                    lead = f"<b>{n} plików</b> pasujących do reguł jest już"
                self.tracked_bar.html = (f"{lead} w repozytorium ({names}). Sama reguła ich nie usunie – "
                                         "wyjmij je z repozytorium, na dysku zostaną.")
                self.tracked_bar._paint()
            self.tracked_bar.setVisible(bool(tracked))

        def fail(msg):
            self.check_btn.setEnabled(True)
            self.check_info.setText("Nie udało się sprawdzić.")
            notify(self, ".gitignore", msg)

        self.run_task(self.repo.match_ignore, self.editor.toPlainText(), on_done=done, on_error=fail, quiet=True)

    # ---------------------------------------------------------------- zapis
    def _write(self) -> bool:
        text = self.editor.toPlainText()
        if not text.strip() and not self.path.exists():
            return True
        if text and not text.endswith("\n"):
            text += "\n"
        try:
            self.path.write_text(text, encoding="utf-8")
        except OSError as e:
            notify(self, "Nie udało się zapisać", str(e))
            return False
        self.original = self.editor.toPlainText()
        return True

    def _ok(self):
        if self._write():
            self.accept()

    def _save_untrack(self):
        if not self._write():
            return
        try:
            self.repo.stop_tracking(self.tracked)
        except Exception as e:  # noqa: BLE001
            notify(self, "Nie udało się", str(e))
            return
        self.result_msg = (f"Zapisano .gitignore. Wyjęto z repozytorium: {len(self.tracked)} – "
                           "zatwierdź i wyślij zmiany.")
        self.accept()

    def reject(self):
        if self.editor.toPlainText() != self.original and not ask(
                self, "Niezapisane zmiany", "Zamknąć bez zapisywania zmian w .gitignore?", "Odrzuć zmiany",
                danger=True):
            return
        super().reject()


def _head(*widgets) -> QWidget:
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(16, 8, 12, 8)
    h.setSpacing(10)
    for x in widgets:
        h.addWidget(x)
    h.addStretch(1)
    w.setMinimumHeight(48)
    return w
