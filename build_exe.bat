@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\installed.ok" (
    echo Najpierw uruchom run.bat, aby przygotowac srodowisko.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m pip install pyinstaller
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --windowed --onefile --name EasyGit EasyGit.pyw
if errorlevel 1 (
    echo Budowanie nie powiodlo sie.
    pause
    exit /b 1
)
echo.
echo Gotowe: dist\EasyGit.exe
pause
