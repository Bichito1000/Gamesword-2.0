@echo off
setlocal
chcp 65001 >nul
title GAMESWORD - Crear ejecutable
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Primero ejecuta INSTALAR_Y_ABRIR.bat
    pause
    exit /b 1
)
set "VPY=%~dp0.venv\Scripts\python.exe"
"%VPY%" -m pip install pyinstaller
if errorlevel 1 (
    echo [ERROR] No se pudo instalar PyInstaller.
    pause
    exit /b 1
)
set "EXTRA="
"%VPY%" -c "import speech_recognition" >nul 2>&1 && set "EXTRA=--collect-all speech_recognition"
"%VPY%" -m PyInstaller --noconfirm --clean --windowed --name Gamesword ^
    --collect-submodules pyttsx3 --hidden-import pyttsx3.drivers.sapi5 %EXTRA% ^
    main.py
if errorlevel 1 (
    echo [ERROR] La compilacion fallo. Revisa los mensajes de arriba.
    pause
    exit /b 1
)
if defined GAMESWORD_PFX signtool sign /f "%GAMESWORD_PFX%" /p "%GAMESWORD_PFX_PASS%" /tr http://timestamp.digicert.com /td sha256 /fd sha256 "dist\Gamesword\Gamesword.exe"
echo.
echo Listo: dist\Gamesword\Gamesword.exe
if not defined GAMESWORD_PFX echo (Sin firmar: define GAMESWORD_PFX y GAMESWORD_PFX_PASS con tu certificado para firmarlo automaticamente.)
echo Para crear un instalador profesional, abre installer.iss con Inno Setup 6 y pulsa Compilar.
pause
endlocal
