@echo off
setlocal
cd /d "%~dp0"

set "PY=python"
where py >nul 2>nul
if %errorlevel%==0 set "PY=py -3"

if not exist ".venv\installed.ok" (
    echo Pierwsze uruchomienie - przygotowuje srodowisko Python...
    if not exist ".venv" (
        %PY% -m venv .venv
        if errorlevel 1 (
            echo.
            echo Nie znaleziono Pythona. Zainstaluj Python 3.10+ ze strony https://www.python.org/downloads/
            echo i zaznacz opcje "Add python.exe to PATH".
            pause
            exit /b 1
        )
    )
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo Instalacja bibliotek nie powiodla sie.
        pause
        exit /b 1
    )
    echo ok> ".venv\installed.ok"
)

start "" ".venv\Scripts\pythonw.exe" UI-git.pyw
