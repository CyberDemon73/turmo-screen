@echo off
rem Starts Turmo Screen on Windows (creates a local Python environment on first run).
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo First run: setting up Python environment...
    py -3 -m venv .venv 2>nul || python -m venv .venv
    ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
)
start "" ".venv\Scripts\pythonw.exe" -m turmoscreen %*
