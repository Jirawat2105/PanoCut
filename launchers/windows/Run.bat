@echo off
setlocal
cd /d "%~dp0..\.."
if not exist "%~dp0..\..\.venv\Scripts\pythonw.exe" goto install
"%~dp0..\..\.venv\Scripts\python.exe" -c "import PySide6; import PIL" >nul 2>&1
if errorlevel 1 goto install
goto launch
:install
call "%~dp01click install dependencies.bat"
if errorlevel 1 exit /b 1
:launch
start "" /D "%~dp0..\.." "%~dp0..\..\.venv\Scripts\pythonw.exe" "%~dp0..\..\main.py"
exit /b 0
