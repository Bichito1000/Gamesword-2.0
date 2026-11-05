@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo Primero ejecuta INSTALAR_Y_ABRIR.bat
    pause
    exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" main.py
