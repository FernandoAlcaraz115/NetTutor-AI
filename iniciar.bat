@echo off
title NetTutorIA - Laboratorio Inteligente
echo ======================================================
echo           Iniciando NetTutorIA...
echo ======================================================
echo Abriendo aplicacion en tu navegador...
cd /d "%~dp0"
start http://localhost:8000
python backend/run.py
pause
