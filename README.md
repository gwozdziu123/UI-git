# EasyGit

Prosta aplikacja okienkowa (Windows) do zarządzania repozytoriami na GitHubie:
powiązujesz lokalny folder z repozytorium i wysyłasz zmiany jednym przyciskiem.

## Wymagania

- **Git for Windows** – https://git-scm.com/download/win (wersja 2.31 lub nowsza)
- **Python 3.10+** – https://www.python.org/downloads/ (przy instalacji zaznacz *Add python.exe to PATH*)

## Uruchomienie

1. Kliknij dwukrotnie **`run.bat`**. Przy pierwszym uruchomieniu skrypt utworzy środowisko `.venv`
   i zainstaluje biblioteki (PySide6, requests, keyring) – to potrwa ok. minuty.
2. Kolejne uruchomienia: znowu `run.bat` (startuje od razu, bez okna konsoli).

Własny plik `.exe`: uruchom `build_exe.bat` → wynik w `dist\EasyGit.exe`
(można go skopiować w dowolne miejsce; Git nadal musi być zainstalowany).

## Pierwsze kroki

1. **Zaloguj do GitHuba** → *Utwórz token na GitHubie* → ustaw ważność → *Generate token* → wklej token.
   Token trafia do Menedżera poświadczeń Windows (nie do pliku).
2. Podłącz projekt:
   - **Powiąż folder** – istniejący folder na dysku + repozytorium z listy (albo wklejony adres),
   - **Nowe repozytorium** – tworzy repozytorium na GitHubie i od razu wiąże je z folderem,
   - **Sklonuj** – pobiera repozytorium z GitHuba do nowego folderu.
3. Zakładka **Zmiany**: zaznacz pliki, wpisz opis i kliknij **Zatwierdź i wyślij**.

## Funkcje

| Miejsce | Co robi |
|---|---|
| Moje projekty | lista powiązanych folderów z gałęzią, liczbą zmian i stanem ↑/↓ |
| GitHub | Twoje repozytoria (wyszukiwanie, klonowanie, wiązanie, otwieranie w przeglądarce) |
| Zmiany | lista zmienionych plików z podglądem różnic, wybór plików do commita |
| Prawy klik na pliku | otwórz, pokaż w folderze, ignoruj (plik / rozszerzenie / folder), cofnij zmiany |
| Pobierz / Wyślij | `git pull` / `git push` (pierwsze wysłanie ustawia śledzenie gałęzi) |
| Historia | ostatnie 300 commitów, podgląd zmian w każdym z nich |
| .gitignore… | wbudowane szablony (Python, C#, TIA Portal, GX Works, Office…) + szablony z GitHuba |
| Dziennik | polecenia git wykonane przez aplikację i ich wynik |

## Dobrze wiedzieć

- **Powiązanie folderu nie nadpisuje plików.** Jeśli repozytorium na GitHubie ma już historię, a folder
  nie był repozytorium git, aplikacja przejmuje historię z GitHuba, a różnice w Twoich plikach
  pokazuje jako zmiany do zatwierdzenia.
- Pliki **większe niż 100 MB** są wykrywane przed commitem (GitHub ich nie przyjmie) – aplikacja proponuje dodanie ich do `.gitignore`.
- **Konflikty** po pobraniu: pojawi się żółty pasek. Popraw w pliku fragmenty między `<<<<<<<` a `>>>>>>>`
  i zatwierdź – albo kliknij *Przerwij scalanie*.
- Autor commitów: Twoja konfiguracja `git config user.name/user.email`, a jeśli jej nie ma – dane z konta GitHub.
- Token jest przekazywany do gita przez zmienne środowiskowe tylko na czas operacji – nie jest zapisywany
  w `.git/config` ani w adresie repozytorium.
- Ustawienia (lista projektów): `%APPDATA%\EasyGit\config.json`.

## Wygląd

Interfejs korzysta z design systemu el_Fuszka: jasne tło `#f2f4f8`, treść na białych kartach (promień 14 px),
jeden niebieski akcent `#1d4ed8`, statusy zawsze z kolorową kropką i słowem, ikony liniowe 24×24, toasty
potwierdzające („Zatwierdzono”, „Wysłano na GitHuba”). Motyw ciemny włącza się automatycznie razem z ustawieniem
Windows. Do podglądu konkretnego motywu: `set EASYGIT_THEME=dark` (albo `light`) przed uruchomieniem.

## Struktura

```
EasyGit.pyw              start aplikacji (bez konsoli)
easy_git/app.py          okno główne
easy_git/dialogs.py      okna: logowanie, powiązanie, nowe repo, klonowanie, .gitignore
easy_git/git_ops.py      operacje git (status, commit, push, pull, historia…)
easy_git/github_api.py   GitHub REST API (konto, lista repo, tworzenie repo)
easy_git/config.py       ustawienia + token w Menedżerze poświadczeń
easy_git/theme.py        tokeny design systemu (kolory jasny/ciemny, typografia) → arkusz stylów Qt
easy_git/icons.py        zestaw ikon liniowych z design systemu
easy_git/widgets.py      komponenty: karta, wiersze list, badge statusu, baner, toast, pusty stan
```
