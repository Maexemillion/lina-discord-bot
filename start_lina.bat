@echo off
echo Starte Lina Bot...

REM Zum Ordner des Scripts wechseln
cd /d "%~dp0"

REM Venv aktivieren
call .venv\Scripts\activate.bat

REM Bot starten
python bot.py

echo.
echo Bot wurde beendet. Druecke eine Taste zum Schliessen...
pause
