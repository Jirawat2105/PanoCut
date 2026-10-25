@echo off
setlocal
cd /d "%~dp0..\.."
if not exist ".venv\Scripts\python.exe" call "%~dp01click install dependencies.bat"
if not exist ".venv\Scripts\python.exe" exit /b 1
".venv\Scripts\python.exe" -m pip install "pyinstaller>=6.11,<7"
if errorlevel 1 goto failed
".venv\Scripts\python.exe" scripts\build.py
if errorlevel 1 goto failed
echo.
echo Ready: dist\PanoTess.exe
echo This single EXE includes its runtime and can be copied to another Windows x64 PC.
pause
exit /b 0
:failed
echo Build failed. See the error above.
pause
exit /b 1
