"""Ustawienia aplikacji: lista powiązanych folderów (JSON) i token (Menedżer poświadczeń Windows)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional

SERVICE = "EasyGit"
TOKEN_KEY = "github_token"


def config_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home()))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    d = base / "EasyGit"
    d.mkdir(parents=True, exist_ok=True)
    return d


class Config:
    def __init__(self, path: Optional[Path] = None):
        self.path = path or config_dir() / "config.json"
        self.data = {"projects": [], "clone_dir": str(Path.home() / "GitHub")}
        self.load()

    def load(self):
        try:
            self.data.update(json.loads(self.path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass

    def save(self):
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)

    @property
    def projects(self) -> list[str]:
        return self.data["projects"]

    def add_project(self, path: str):
        path = str(Path(path))
        norm = os.path.normcase(os.path.abspath(path))
        if not any(os.path.normcase(os.path.abspath(p)) == norm for p in self.projects):
            self.projects.append(path)
            self.save()

    def remove_project(self, path: str):
        if path in self.projects:
            self.projects.remove(path)
            self.save()

    @property
    def clone_dir(self) -> str:
        return self.data.get("clone_dir") or str(Path.home() / "GitHub")

    @clone_dir.setter
    def clone_dir(self, v: str):
        self.data["clone_dir"] = v
        self.save()


# ---- token ------------------------------------------------------------
def _keyring():
    try:
        import keyring
        return keyring
    except Exception:
        return None


def load_token() -> Optional[str]:
    kr = _keyring()
    if not kr:
        return None
    try:
        return kr.get_password(SERVICE, TOKEN_KEY)
    except Exception:
        return None


def save_token(token: str) -> bool:
    kr = _keyring()
    if not kr:
        return False
    try:
        kr.set_password(SERVICE, TOKEN_KEY, token)
        return True
    except Exception:
        return False


def delete_token():
    kr = _keyring()
    if kr:
        try:
            kr.delete_password(SERVICE, TOKEN_KEY)
        except Exception:
            pass
