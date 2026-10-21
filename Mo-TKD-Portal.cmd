@echo off
powershell.exe -NoProfile -File "%~dp0Open-Portal.ps1"
if errorlevel 1 pause
