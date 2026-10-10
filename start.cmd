@echo off
rem Double-click to run Sarenakh. Windows blocks .ps1 files by default, so this runs start.ps1 for you.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1"
pause
