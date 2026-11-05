@echo off
setlocal
chcp 65001 >nul
title GAMESWORD - Certificado HTTPS
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" goto :noenv
set "VPY=%~dp0.venv\Scripts\python.exe"
"%VPY%" -m pip install cryptography
if errorlevel 1 goto :fail
set /p IP=Escribe la IP de este PC que usaran tus amigos, por ejemplo 192.168.1.50: 
"%VPY%" -m server.make_cert --ip %IP%
if errorlevel 1 goto :fail
echo.
echo Listo. Ahora ejecuta INICIAR_SERVIDOR.bat: usara HTTPS automaticamente.
echo En Gamesword, Ajustes - Online, desactiva Verificar certificado, porque este certificado es autofirmado.
goto :end
:noenv
echo Primero ejecuta INSTALAR_Y_ABRIR.bat
goto :end
:fail
echo [ERROR] No se pudo crear el certificado.
:end
pause
endlocal
