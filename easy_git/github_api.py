"""Minimalny klient GitHub REST API."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import requests

API = "https://api.github.com"


class GitHubError(Exception):
    pass


@dataclass
class GhUser:
    login: str
    name: str
    id: int
    email: str

    @property
    def commit_email(self) -> str:
        return self.email or f"{self.id}+{self.login}@users.noreply.github.com"


@dataclass
class GhRepo:
    full_name: str
    name: str
    owner: str
    private: bool
    description: str
    clone_url: str
    html_url: str
    default_branch: str
    updated_at: str
    empty: bool


class GitHub:
    def __init__(self, token: Optional[str]):
        self.token = token
        self.s = requests.Session()
        self.s.headers.update({
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "EasyGit",
        })
        if token:
            self.s.headers["Authorization"] = f"Bearer {token}"

    def _req(self, method: str, path: str, **kw):
        url = path if path.startswith("http") else API + path
        try:
            r = self.s.request(method, url, timeout=30, **kw)
        except requests.RequestException as e:
            raise GitHubError(f"Brak połączenia z GitHubem: {e}")
        if r.status_code == 401:
            raise GitHubError("Token jest nieprawidłowy lub wygasł (401).")
        if r.status_code == 403 and "rate limit" in r.text.lower():
            raise GitHubError("Przekroczono limit zapytań GitHub API. Spróbuj za chwilę.")
        if r.status_code >= 400:
            try:
                data = r.json()
                msg = data.get("message", "")
                errs = data.get("errors") or []
                details = "; ".join(e.get("message", str(e)) if isinstance(e, dict) else str(e) for e in errs)
                msg = f"{msg} {details}".strip()
            except ValueError:
                msg = r.text[:300]
            raise GitHubError(f"GitHub: {msg} ({r.status_code})")
        return r

    def user(self) -> GhUser:
        d = self._req("GET", "/user").json()
        return GhUser(login=d["login"], name=d.get("name") or d["login"], id=d["id"], email=d.get("email") or "")

    @staticmethod
    def _repo(d: dict) -> GhRepo:
        return GhRepo(
            full_name=d["full_name"], name=d["name"], owner=d["owner"]["login"], private=d["private"],
            description=d.get("description") or "", clone_url=d["clone_url"], html_url=d["html_url"],
            default_branch=d.get("default_branch") or "main", updated_at=(d.get("pushed_at") or d.get("updated_at") or "")[:10],
            empty=(d.get("size", 0) == 0),
        )

    def repos(self) -> list[GhRepo]:
        out: list[GhRepo] = []
        url = f"{API}/user/repos?per_page=100&sort=updated&affiliation=owner,collaborator,organization_member"
        while url:
            r = self._req("GET", url)
            out += [self._repo(d) for d in r.json()]
            url = r.links.get("next", {}).get("url")
        return out

    def create_repo(self, name: str, description: str = "", private: bool = True, auto_init: bool = False) -> GhRepo:
        payload = {"name": name, "description": description, "private": private, "auto_init": auto_init}
        return self._repo(self._req("POST", "/user/repos", json=payload).json())

    def gitignore_templates(self) -> list[str]:
        return self._req("GET", "/gitignore/templates").json()

    def gitignore_template(self, name: str) -> str:
        return self._req("GET", f"/gitignore/templates/{name}").json().get("source", "")
