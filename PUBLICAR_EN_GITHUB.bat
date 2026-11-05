@echo off
setlocal
chcp 65001 >nul
title GAMESWORD - Publicar en GitHub
cd /d "%~dp0"

where git >nul 2>&1
if errorlevel 1 goto :nogit

git config user.name >nul 2>&1
if errorlevel 1 goto :noid
git config user.email >nul 2>&1
if errorlevel 1 goto :noid

echo.
echo 1) Crea en github.com un repositorio VACIO (sin README ni licencia): boton New repository.
echo 2) Copia su direccion, por ejemplo  https://github.com/TU-USUARIO/gamesword.git
echo.
set /p URL=Pega aqui la direccion del repositorio: 
if "%URL%"=="" goto :nourl

if not exist ".git" git init -b main
git add .
git commit -m "Gamesword 2.0.0"
git branch -M main
git remote remove origin >nul 2>&1
git remote add origin %URL%
echo.
echo Subiendo... Si se abre una ventana del navegador, inicia sesion en GitHub.
git push -u origin main
if errorlevel 1 goto :pushfail
echo.
echo Listo: tu proyecto ya esta en GitHub.
goto :end

:nogit
echo Necesitas instalar Git: https://git-scm.com/download/win   Despues vuelve a ejecutar este archivo.
goto :end

:noid
echo Git necesita saber quien eres. Abre una terminal y ejecuta estas dos lineas con TUS datos:
echo   git config --global user.name "Tu Nombre"
echo   git config --global user.email "tu-correo@ejemplo.com"
echo Despues vuelve a ejecutar este archivo.
goto :end

:nourl
echo No has pegado ninguna direccion.
goto :end

:pushfail
echo.
echo [ERROR] No se pudo subir. Comprueba la direccion, que el repositorio este vacio y que hayas iniciado sesion.
:end
echo.
pause
endlocal
