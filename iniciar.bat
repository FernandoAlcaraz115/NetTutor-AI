@echo off
title NetTutorIA - Laboratorio Inteligente
echo ======================================================
echo           Iniciando NetTutorIA...
echo ======================================================
cd /d "%~dp0"

echo Verificando dependencias...
python -c "import fastapi, uvicorn, pydantic, dotenv" >nul 2>&1
if %errorlevel% neq 0 (
    echo Instalando dependencias necesarias...
    pip install -r backend\requirements.txt
)

echo Abriendo aplicacion en tu navegador...
start "" cmd /c "timeout /t 3 /nobreak >nul & start http://localhost:8000"
python backend\run.py

if %errorlevel% neq 0 (
    echo.
    echo Ocurrio un error al ejecutar NetTutorIA.
)
pause
