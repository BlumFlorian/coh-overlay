@echo off
rem Wertet alle gespeicherten L1-Analysen aus (Vorhersage gegen Wirklichkeit) und oeffnet den Bericht.
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Die Python-Umgebung .venv fehlt. Siehe README.md, Abschnitt "Setup".
    pause
    exit /b 1
)
".venv\Scripts\python.exe" tools\replay.py %*
if errorlevel 1 (
    echo.
    echo Die Auswertung wurde mit einem Fehler beendet. Siehe Meldung oben.
    pause
    exit /b 1
)
for /f "delims=" %%f in ('dir /b /o-d "dataset\replay\bericht_*.md"') do (
    start "" "dataset\replay\%%f"
    goto :done
)
:done
endlocal
