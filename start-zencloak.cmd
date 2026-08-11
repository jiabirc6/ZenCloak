@echo off
cd /d "%~dp0"
set "PYTHONPATH=%~dp0src"
set "PYW=%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe"
if not exist "%PYW%" set "PYW=pythonw.exe"
start "" "%PYW%" -m zencloak
