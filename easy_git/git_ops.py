"""Operacje na lokalnych repozytoriach – cienka nakładka na program `git`."""
from __future__ import annotations

import base64
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

# Callback do dziennika: (polecenie, wynik)
LogFn = Optional[Callable[[str, str], None]]

GITHUB_LIMIT_BYTES = 100 * 1024 * 1024  # GitHub odrzuca pliki > 100 MB

# Polecenia zapisywane w dzienniku (operacje tylko do odczytu są pomijane).
LOGGED = {"init", "remote", "fetch", "reset", "branch", "add", "rm", "commit", "push", "pull", "clone",
          "checkout", "merge", "symbolic-ref"}


class GitError(Exception):
    pass


@dataclass
class FileChange:
    path: str
    index: str  # status w indeksie (X)
    worktree: str  # status w katalogu roboczym (Y)
    orig_path: str = ""

    @property
    def kind(self) -> str:
        x, y = self.index, self.worktree
        if x == "?" and y == "?":
            return "nowy"
        if "U" in (x, y) or (x == y and x in "AD"):
            return "konflikt"
        if "D" in (x, y):
            return "usunięty"
        if "R" in (x, y):
            return "przeniesiony"
        if "A" in (x, y):
            return "dodany"
        return "zmieniony"


@dataclass
class RepoInfo:
    path: str
    is_repo: bool = False
    branch: str = ""
    has_commits: bool = False
    remote_url: str = ""
    upstream: str = ""
    ahead: int = 0
    behind: int = 0
    merging: bool = False
    changes: list[FileChange] = field(default_factory=list)


@dataclass
class Commit:
    sha: str
    short: str
    author: str
    date: str
    subject: str


def git_executable() -> Optional[str]:
    return shutil.which("git")


def git_version() -> str:
    exe = git_executable()
    if not exe:
        return ""
    try:
        return run_git(["--version"], cwd=None).strip()
    except GitError:
        return ""


def _auth_env(token: Optional[str]) -> dict:
    """Przekazuje token do gita przez zmienne środowiskowe (nie trafia do argumentów ani do .git/config)."""
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    if token:
        basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        pairs = [
            ("http.https://github.com/.extraheader", f"AUTHORIZATION: basic {basic}"),
            ("credential.helper", ""),
        ]
        env["GIT_CONFIG_COUNT"] = str(len(pairs))
        for i, (k, v) in enumerate(pairs):
            env[f"GIT_CONFIG_KEY_{i}"] = k
            env[f"GIT_CONFIG_VALUE_{i}"] = v
    return env


def run_git(
    args: list[str],
    cwd: Optional[str],
    token: Optional[str] = None,
    input_text: Optional[str] = None,
    log: LogFn = None,
    timeout: int = 600,
    check: bool = True,
) -> str:
    exe = git_executable()
    if not exe:
        raise GitError("Nie znaleziono programu git. Zainstaluj Git for Windows: https://git-scm.com/download/win")
    cmd = [exe, "-c", "core.quotepath=false", "-c", "color.ui=never", *args]
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            input=input_text,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=_auth_env(token),
            timeout=timeout,
            **kwargs,
        )
    except subprocess.TimeoutExpired:
        raise GitError(f"Przekroczono czas oczekiwania: git {' '.join(args)}")
    out = (proc.stdout or "") + (proc.stderr or "")
    if log:
        log("git " + " ".join(args), out.strip())
    if check and proc.returncode != 0:
        msg = "\n".join(x.strip() for x in (proc.stderr, proc.stdout) if x and x.strip())
        raise GitError(msg or f"git zakończył się kodem {proc.returncode}")
    return proc.stdout


class Repo:
    def __init__(self, path: str, token: Optional[str] = None, log: LogFn = None):
        self.path = str(Path(path))
        self.token = token
        self.log = log

    # ---- pomocnicze -------------------------------------------------
    def git(self, *args: str, input_text: Optional[str] = None, check: bool = True, auth: bool = False) -> str:
        sub = next((a for a in args if not a.startswith("-") and "=" not in a), "")
        return run_git(list(args), cwd=self.path, token=self.token if auth else None,
                       input_text=input_text, log=self.log if sub in LOGGED else None, check=check)

    def _try(self, *args: str) -> str:
        try:
            return run_git(list(args), cwd=self.path, check=True).strip()
        except GitError:
            return ""

    # ---- informacje -------------------------------------------------
    def is_repo(self) -> bool:
        if not Path(self.path).is_dir():
            return False
        top = self._try("rev-parse", "--show-toplevel")
        if not top:
            return False
        return os.path.normcase(os.path.abspath(top)) == os.path.normcase(os.path.abspath(self.path))

    def has_commits(self) -> bool:
        return bool(self._try("rev-parse", "--verify", "-q", "HEAD"))

    def branch(self) -> str:
        return self._try("symbolic-ref", "--short", "-q", "HEAD") or self._try("rev-parse", "--short", "HEAD")

    def remote_url(self, name: str = "origin") -> str:
        return self._try("remote", "get-url", name)

    def upstream(self) -> str:
        return self._try("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")

    def ahead_behind(self) -> tuple[int, int]:
        out = self._try("rev-list", "--left-right", "--count", "HEAD...@{u}")
        if not out:
            return 0, 0
        a, b = out.split()
        return int(a), int(b)

    def status(self) -> list[FileChange]:
        out = self.git("status", "--porcelain=v1", "-z", "-uall")
        parts = out.split("\0")
        changes: list[FileChange] = []
        i = 0
        while i < len(parts):
            entry = parts[i]
            i += 1
            if len(entry) < 4:
                continue
            x, y, path = entry[0], entry[1], entry[3:]
            orig = ""
            if x in "RC" or y in "RC":
                orig = parts[i] if i < len(parts) else ""
                i += 1
            changes.append(FileChange(path=path, index=x, worktree=y, orig_path=orig))
        return changes

    def info(self) -> RepoInfo:
        info = RepoInfo(path=self.path)
        if not self.is_repo():
            return info
        info.is_repo = True
        info.branch = self.branch()
        info.has_commits = self.has_commits()
        info.remote_url = self.remote_url()
        info.upstream = self.upstream() if info.has_commits else ""
        if info.upstream:
            info.ahead, info.behind = self.ahead_behind()
        info.merging = self.is_merging()
        info.changes = self.status()
        return info

    def is_merging(self) -> bool:
        return bool(self._try("rev-parse", "-q", "--verify", "MERGE_HEAD"))

    def abort_merge(self) -> None:
        self.git("merge", "--abort")

    def unresolved_conflicts(self) -> list[str]:
        bad = []
        for c in self.status():
            if c.kind != "konflikt":
                continue
            f = Path(self.path) / c.path
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if any(ln.startswith("<<<<<<< ") for ln in text.splitlines()):
                bad.append(c.path)
        return bad

    def log_commits(self, limit: int = 300) -> list[Commit]:
        if not self.has_commits():
            return []
        fmt = "%H%x1f%h%x1f%an%x1f%ad%x1f%s%x1e"
        out = self.git("log", f"-n{limit}", f"--pretty=format:{fmt}", "--date=format:%d.%m.%Y %H:%M")
        commits = []
        for rec in out.split("\x1e"):
            rec = rec.strip("\n")
            if not rec:
                continue
            f = rec.split("\x1f")
            if len(f) >= 5:
                commits.append(Commit(*f[:5]))
        return commits

    def show_commit(self, sha: str) -> str:
        return self.git("show", "--stat", "--patch", "--date=format:%d.%m.%Y %H:%M", "--format=commit %H%nAutor: %an <%ae>%nData:  %ad%n%n    %B", sha)

    def file_diff(self, change: FileChange) -> str:
        full = Path(self.path) / change.path
        if change.kind == "nowy":
            if full.is_dir():
                return ""
            try:
                size = full.stat().st_size
            except OSError:
                return "(nie można odczytać pliku)"
            if size > 512 * 1024:
                return f"Nowy plik ({size / 1024 / 1024:.1f} MB) – zbyt duży do podglądu."
            data = full.read_bytes()
            if b"\0" in data[:8000]:
                return f"Nowy plik binarny ({size} B)."
            text = data.decode("utf-8", errors="replace")
            return f"Nowy plik: {change.path}\n" + "\n".join("+" + ln for ln in text.splitlines())
        args = ["diff"]
        if self.has_commits():
            args.append("HEAD")
        else:
            args.append("--cached")
        args += ["--", change.path]
        if change.orig_path:
            args.append(change.orig_path)
        out = self.git(*args, check=False)
        return out or "(brak różnic tekstowych – np. zmiana uprawnień lub plik binarny)"

    def large_files(self, paths: list[str]) -> list[tuple[str, int]]:
        res = []
        for p in paths:
            f = Path(self.path) / p
            try:
                if f.is_file() and f.stat().st_size > GITHUB_LIMIT_BYTES:
                    res.append((p, f.stat().st_size))
            except OSError:
                pass
        return res

    # ---- operacje ---------------------------------------------------
    def init(self, branch: str = "main") -> None:
        Path(self.path).mkdir(parents=True, exist_ok=True)
        try:
            self.git("init", "-b", branch)
        except GitError:
            self.git("init")
            self.git("symbolic-ref", "HEAD", f"refs/heads/{branch}")

    def set_remote(self, url: str, name: str = "origin") -> None:
        if self.remote_url(name):
            self.git("remote", "set-url", name, url)
        else:
            self.git("remote", "add", name, url)

    def fetch(self) -> None:
        self.git("fetch", "--prune", "origin", auth=True)

    def remote_branch_exists(self, branch: str) -> bool:
        return bool(self._try("rev-parse", "--verify", "-q", f"refs/remotes/origin/{branch}"))

    def link_to_remote(self, url: str, default_branch: str = "main") -> str:
        """Wiąże folder z repozytorium zdalnym. Zwraca opis tego, co zrobiono."""
        notes = []
        if not self.is_repo():
            self.init(default_branch)
            notes.append("Utworzono nowe repozytorium git w folderze.")
        self.set_remote(url)
        notes.append(f"Ustawiono zdalne repozytorium origin → {url}")
        try:
            self.fetch()
        except GitError as e:
            notes.append(f"Nie udało się pobrać danych z GitHuba: {e}")
            return "\n".join(notes)
        if not self.has_commits():
            # Lokalnie pusto: przejmij historię z GitHuba, zostawiając lokalne pliki jako zmiany.
            cur = self.branch() or default_branch
            target = default_branch if self.remote_branch_exists(default_branch) else (
                cur if self.remote_branch_exists(cur) else "")
            if target:
                if cur != target:
                    self.git("symbolic-ref", "HEAD", f"refs/heads/{target}")
                self.git("reset", "-q", f"origin/{target}")
                self.git("branch", f"--set-upstream-to=origin/{target}")
                notes.append(f"Połączono z istniejącą historią gałęzi '{target}'. "
                             "Pliki różniące się od GitHuba widać jako zmiany.")
            else:
                notes.append("Repozytorium na GitHubie jest puste – zrób pierwszy commit i wyślij.")
        else:
            br = self.branch()
            if self.remote_branch_exists(br) and not self.upstream():
                self.git("branch", f"--set-upstream-to=origin/{br}")
                notes.append(f"Gałąź '{br}' śledzi teraz origin/{br}.")
        return "\n".join(notes)

    def commit(self, paths: list[str], message: str, name: str = "", email: str = "") -> str:
        if not paths:
            raise GitError("Nie zaznaczono żadnych plików.")
        if not message.strip():
            raise GitError("Wpisz opis zmian (wiadomość commita).")
        ident = []
        if not self._try("config", "user.name") and name:
            ident += ["-c", f"user.name={name}"]
        if not self._try("config", "user.email") and email:
            ident += ["-c", f"user.email={email}"]
        if self.is_merging():
            # Commit scalający musi zawierać wszystkie pliki.
            bad = self.unresolved_conflicts()
            if bad:
                raise GitError("Te pliki nadal zawierają znaczniki konfliktu (<<<<<<<):\n" + "\n".join(bad))
            self.git("add", "-A")
            return self.git(*ident, "commit", "-F", "-", input_text=message.strip() + "\n")
        # Wyczyść indeks, potem dodaj tylko zaznaczone pliki.
        if self.has_commits():
            self.git("reset", "-q")
        else:
            self.git("rm", "-r", "-q", "--cached", "--ignore-unmatch", ".")
        self.git("add", "-A", "--pathspec-from-file=-", "--pathspec-file-nul", input_text="\0".join(paths) + "\0")
        return self.git(*ident, "commit", "-F", "-", input_text=message.strip() + "\n")

    def push(self) -> str:
        br = self.branch()
        if not br:
            raise GitError("Brak aktywnej gałęzi.")
        if not self.remote_url():
            raise GitError("Folder nie jest powiązany z repozytorium na GitHubie.")
        if self.upstream():
            return run_git(["push"], self.path, self.token, log=self.log, check=True) or "Wysłano."
        return run_git(["push", "-u", "origin", br], self.path, self.token, log=self.log) or "Wysłano."

    def pull(self) -> str:
        if not self.remote_url():
            raise GitError("Folder nie jest powiązany z repozytorium na GitHubie.")
        if not self.has_commits():
            self.fetch()
            br = self.branch()
            if self.remote_branch_exists(br):
                self.git("reset", "-q", f"origin/{br}")
                self.git("branch", f"--set-upstream-to=origin/{br}")
                return "Pobrano historię z GitHuba."
            return "Repozytorium na GitHubie jest puste."
        if not self.upstream():
            self.fetch()
            br = self.branch()
            if not self.remote_branch_exists(br):
                return f"Gałąź '{br}' nie istnieje jeszcze na GitHubie – użyj 'Wyślij'."
            self.git("branch", f"--set-upstream-to=origin/{br}")
        out = run_git(["pull", "--no-rebase", "--no-edit"], self.path, self.token, log=self.log)
        return out.strip() or "Pobrano."

    def discard(self, change: FileChange) -> None:
        """Cofa zmiany w pliku (nowe pliki usuwa)."""
        full = Path(self.path) / change.path
        if change.kind == "nowy":
            if full.is_file():
                full.unlink()
            return
        if self.has_commits():
            self.git("checkout", "HEAD", "--", change.path)
            if change.orig_path:
                self.git("checkout", "HEAD", "--", change.orig_path, check=False)
        else:
            self.git("rm", "-q", "--cached", "--", change.path, check=False)

    def ignore(self, pattern: str) -> None:
        gi = Path(self.path) / ".gitignore"
        existing = gi.read_text(encoding="utf-8", errors="replace") if gi.exists() else ""
        lines = existing.splitlines()
        if pattern in lines:
            return
        sep = "" if (not existing or existing.endswith("\n")) else "\n"
        gi.write_text(existing + sep + pattern + "\n", encoding="utf-8")


def clone(url: str, dest: str, token: Optional[str], log: LogFn = None) -> str:
    parent = str(Path(dest).parent)
    Path(parent).mkdir(parents=True, exist_ok=True)
    return run_git(["clone", url, dest], cwd=parent, token=token, log=log)
