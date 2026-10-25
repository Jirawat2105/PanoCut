@echo off
setlocal
cd /d "%~dp0..\.."
title PanoTess - Install dependencies
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\..\scripts\install.ps1"
if errorlevel 1 goto failed
echo.
echo Installation finished. Double-click "Run.bat" to start.
pause
exit /b 0
:failed
echo.
echo Installation failed. See the error above and installation.log in this folder.
pause
exit /b 1
