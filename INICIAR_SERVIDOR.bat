@echo off
setlocal
chcp 65001 >nul
title GAMESWORD - Servidor de amigos
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Primero ejecuta INSTALAR_Y_ABRIR.bat para preparar el entorno.
    pause
    exit /b 1
)
set "VPY=%~dp0.venv\Scripts\python.exe"

"%VPY%" -c "import fastapi, uvicorn" >nul 2>&1
if errorlevel 1 (
    echo Instalando FastAPI y Uvicorn...
    "%VPY%" -m pip install -r requirements-server.txt
    if errorlevel 1 (
        echo [ERROR] No se pudo instalar el servidor.
        pause
        exit /b 1
    )
)

echo.
echo Quieres que tus amigos se conecten desde tu red local o Internet?
echo   S = aceptar conexiones externas (Windows puede pedir permiso en el firewall)
echo   N = solo este PC (para probar)
choice /c SN /n /m "Elige S o N: "
if errorlevel 2 (set "HOST=127.0.0.1") else (set "HOST=0.0.0.0")

set "SSL="
if exist "data\cert.pem" if exist "data\key.pem" set "SSL=--ssl-certfile data\cert.pem --ssl-keyfile data\key.pem"
echo.
if defined SSL (echo Certificado HTTPS encontrado: usa https://TU-IP:8000 en Gamesword.) else echo En Gamesword, pestana Amigos, usa  http://TU-IP:8000  o http://127.0.0.1:8000 en este PC. Para HTTPS ejecuta CREAR_CERTIFICADO_HTTPS.bat
"%VPY%" -m server --host %HOST% --port 8000 %SSL%
pause
endlocal
