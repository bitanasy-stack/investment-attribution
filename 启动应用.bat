@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" goto fail
".venv\Scripts\python.exe" bootstrap.py
".venv\Scripts\python.exe" -m streamlit run app.py
if errorlevel 1 pause
exit /b
:fail
echo Please run the setup BAT file first. See README.md.
pause
exit /b 1
