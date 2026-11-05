@echo off
setlocal
chcp 65001 >nul
title GAMESWORD - Crear ejecutable
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" goto :noenv
set "VPY=%~dp0.venv\Scripts\python.exe"
"%VPY%" -m pip install pyinstaller
if errorlevel 1 goto :fail
"%VPY%" tools\build_exe.py
if errorlevel 1 goto :fail
if defined GAMESWORD_PFX signtool sign /f "%GAMESWORD_PFX%" /p "%GAMESWORD_PFX_PASS%" /tr http://timestamp.digicert.com /td sha256 /fd sha256 "dist\Gamesword\Gamesword.exe"
echo.
echo Listo: dist\Gamesword\Gamesword.exe
echo Para crear un instalador, abre installer.iss con Inno Setup 6 y pulsa Compilar.
goto :end
:noenv
echo Primero ejecuta INSTALAR_Y_ABRIR.bat
goto :end
:fail
echo [ERROR] La compilacion fallo. Revisa los mensajes de arriba.
:end
pause
endlocal
