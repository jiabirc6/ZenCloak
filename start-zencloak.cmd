@echo off
cd /d "%~dp0"
set PYTHONPATH=%~dp0src
python -m zencloak
if errorlevel 1 pause
