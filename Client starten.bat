@echo off
rem Startet den CoH-Berater-Client (Fenster mit Brett-Ansicht, Korrekturen, Overlay-Steuerung).
rem Das Overlay wird im Client ueber "Overlay starten" gestartet (nicht zusaetzlich die andere .bat).
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\pythonw.exe" (
    echo Die Python-Umgebung .venv fehlt. Siehe README.md, Abschnitt "Setup".
    pause
    exit /b 1
)

".venv\Scripts\python.exe" -c "import PySide6" 2>nul
if errorlevel 1 (
    echo PySide6 fehlt. Installation: .venv\Scripts\python -m pip install -r requirements.txt
    pause
    exit /b 1
)

start "" ".venv\Scripts\pythonw.exe" tools\client.py --start %*
endlocal
