@echo off
setlocal
chcp 65001 >nul
title GAMESWORD - Instalacion
cd /d "%~dp0"

echo ================================================
echo    GAMESWORD - Todos tus juegos. Una sola experiencia.
echo ================================================
echo.

if /I "%~1"=="--reinstall" if exist ".venv\.deps_ok" del ".venv\.deps_ok"

echo [1/4] Buscando Python...
set "PY="
where py >nul 2>&1
if not errorlevel 1 set "PY=py -3"
if not defined PY where python >nul 2>&1
if not defined PY if not errorlevel 1 set "PY=python"
if not defined PY goto :nopython
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if errorlevel 1 goto :badpython
echo       Python encontrado.

echo.
echo [2/4] Preparando entorno virtual...
if exist ".venv\Scripts\python.exe" goto :venv_ok
%PY% -m venv .venv
if errorlevel 1 goto :venv_fail
:venv_ok
set "VPY=%~dp0.venv\Scripts\python.exe"

echo.
echo [3/4] Instalando dependencias, solo la primera vez...
if exist ".venv\.deps_ok" goto :deps_done
"%VPY%" -m pip install --upgrade pip
"%VPY%" -m pip install -r requirements.txt
if errorlevel 1 goto :deps_fail
echo ok> ".venv\.deps_ok"
echo.
echo       Instalando reconocimiento de voz, opcional...
"%VPY%" -m pip install -r requirements-voz.txt
if errorlevel 1 echo       [AVISO] No se pudo instalar el reconocimiento de voz. El resto funciona igual.
echo.
echo       Instalando extras opcionales: Discord Rich Presence...
"%VPY%" -m pip install -r requirements-extra.txt
if errorlevel 1 echo       [AVISO] Rich Presence no instalado. El resto funciona igual.
goto :run
:deps_done
echo       Ya instaladas.

:run
echo.
echo [4/4] Iniciando Gamesword...
"%VPY%" main.py
if errorlevel 1 goto :app_fail
goto :end

:nopython
echo.
echo [ERROR] No se encontro Python.
echo         Instala Python 3.10 o superior desde https://www.python.org/downloads/
echo         y marca la casilla Add python.exe to PATH. Despues vuelve a ejecutar este archivo.
goto :end

:badpython
echo.
echo [ERROR] Gamesword necesita Python 3.10 o superior, y el que hay no sirve o no funciona.
echo         Si Windows abre la Microsoft Store, instala Python desde python.org.
goto :end

:venv_fail
echo.
echo [ERROR] No se pudo crear el entorno virtual.
goto :end

:deps_fail
echo.
echo [ERROR] No se pudieron instalar las dependencias. Revisa tu conexion a internet.
echo         Si el mensaje de arriba habla de PySide6, prueba con Python 3.11 o 3.12.
goto :end

:app_fail
echo.
echo [ERROR] Gamesword se cerro con un error. Mira el mensaje de arriba y la carpeta logs.

:end
echo.
pause
endlocal
