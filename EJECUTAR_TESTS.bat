@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Primero ejecuta INSTALAR_Y_ABRIR.bat
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m pip install fastapi uvicorn >nul 2>&1
".venv\Scripts\python.exe" -m unittest discover -s tests -t . -v
pause
