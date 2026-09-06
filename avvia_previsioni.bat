@echo off
chcp 65001 > nul
py "%~dp0previsioni_pioggia_putignano.py"
if %errorlevel% neq 0 (
    python "%~dp0previsioni_pioggia_putignano.py"
)
pause
