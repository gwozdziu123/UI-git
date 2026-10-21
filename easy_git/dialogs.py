"""Okna dialogowe w stylu arkusza (sheet): tytuł, pola z etykietą nad polem, stopka z akcją główną."""
from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFileDialog, QHBoxLayout, QLineEdit, QListWidget,
                               QListWidgetItem, QSplitter, QVBoxLayout, QWidget)

from .gitignore_templates import TEMPLATES
from .widgets import Card, DiffView, button, field, label, notify, separator

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
    """Wybór szablonów .gitignore – wbudowanych i pobieranych z GitHuba."""

    def __init__(self, folder: str, run_task, github, parent=None):
        super().__init__("Szablony .gitignore", "Dopisz do .gitignore", parent, 860)
        self.resize(900, 620)
        self.folder, self.run_task, self.github = folder, run_task, github
        self.remote_cache: dict[str, str] = {}
        self.body.addWidget(label("Zaznacz szablony – reguły zostaną dopisane na końcu pliku .gitignore. "
                                  "Pasujące pliki nie będą wysyłane na GitHuba.", "secondary", wrap=True))
        sp = QSplitter(self)
        sp.setHandleWidth(12)
        left = Card(padding=(4, 4, 4, 8), spacing=6)
        self.list = QListWidget()
        self.list.setObjectName("plain")
        self.list.setSpacing(1)
        for name in TEMPLATES:
            self._add_item(name, ("local", name))
        left.lay.addWidget(self.list, 1)
        self.load_btn = button("Pobierz więcej z GitHuba", "add", "download")
        self.load_btn.clicked.connect(self._load_remote)
        left.lay.addWidget(self.load_btn, 0, Qt.AlignLeft)
        sp.addWidget(left)
        right = Card(padding=(8, 8, 8, 8))
        self.preview = DiffView(highlight=False)
        right.lay.addWidget(self.preview)
        sp.addWidget(right)
        sp.setSizes([300, 560])
        self.body.addWidget(sp, 1)
        self.list.currentItemChanged.connect(self._show)
        gi = Path(folder) / ".gitignore"
        if gi.exists():
            self.preview.show_text("# Obecny .gitignore\n" + gi.read_text(encoding="utf-8", errors="replace"))
        else:
            self.list.setCurrentRow(0)

    def _add_item(self, text, data):
        it = QListWidgetItem(text)
        it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
        it.setCheckState(Qt.Unchecked)
        it.setData(Qt.UserRole, data)
        it.setSizeHint(QSize(0, 38))
        self.list.addItem(it)

    def _load_remote(self):
        self.load_btn.setEnabled(False)
        self.load_btn.setText("Pobieranie…")

        def done(names):
            self.load_btn.setText(f"Pobrano {len(names)} szablonów")
            for n in names:
                self._add_item(f"GitHub: {n}", ("remote", n))

        def fail(msg):
            self.load_btn.setEnabled(True)
            self.load_btn.setText("Pobierz więcej z GitHuba")
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

    def _show(self, item, _prev=None):
        if item:
            self._text_for(item, self.preview.show_text)

    def _ok(self):
        items = [self.list.item(i) for i in range(self.list.count())
                 if self.list.item(i).checkState() == Qt.Checked]
        if not items:
            self.reject()
            return
        missing = [it.data(Qt.UserRole)[1] for it in items
                   if it.data(Qt.UserRole)[0] == "remote" and it.data(Qt.UserRole)[1] not in self.remote_cache]
        if missing:
            pending = set(missing)

            def got(name):
                def _cb(_txt):
                    pending.discard(name)
                    if not pending:
                        self._ok()
                return _cb
            for n in missing:
                self._text_for(next(it for it in items if it.data(Qt.UserRole)[1] == n), got(n))
            return
        gi = Path(self.folder) / ".gitignore"
        existing = gi.read_text(encoding="utf-8", errors="replace") if gi.exists() else ""
        chunks = [existing.rstrip("\n")] if existing.strip() else []
        for it in items:
            kind, name = it.data(Qt.UserRole)
            text = TEMPLATES[name] if kind == "local" else self.remote_cache[name]
            header = f"# ===== {name} ====="
            if header in existing:
                continue
            chunks.append(f"{header}\n{text.strip()}")
        gi.write_text("\n\n".join(chunks) + "\n", encoding="utf-8")
        self.accept()
