@echo off
rem Startet das CoH-Overlay per Doppelklick. Zusaetzliche Argumente werden durchgereicht.
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Die Python-Umgebung .venv fehlt. Siehe README.md, Abschnitt "Setup".
    pause
    exit /b 1
)

".venv\Scripts\python.exe" tools\overlay.py %*

if errorlevel 1 (
    echo.
    echo Das Overlay wurde mit einem Fehler beendet. Siehe Meldung oben.
    pause
)
endlocal
