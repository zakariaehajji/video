@echo off
REM Kick off pending AutoLab renders with venv Python (no Cursor Agent shell needed).
cd /d "%~dp0\.."
".venv\Scripts\python.exe" autolab\run_pending.py
exit /b %ERRORLEVEL%
