@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto install
where py >nul 2>nul
if errorlevel 1 goto usepython
py -3 -m venv .venv
goto check
:usepython
python -m venv .venv
:check
if not exist ".venv\Scripts\python.exe" goto fail
:install
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto fail
".venv\Scripts\python.exe" bootstrap.py
echo Setup finished. Run the start BAT file.
pause
exit /b 0
:fail
echo Setup failed. Python 3.11+ and internet are required. See README.md.
pause
exit /b 1
