@echo off
chcp 65001 > nul
echo ===================================================
echo   INVIO AGGIORNAMENTI SU GITHUB (PUSH)
echo ===================================================
echo.
cd /d "%~dp0"

echo Verifica modifiche locali...
git add .
git diff --cached --quiet
if %ERRORLEVEL% neq 0 (
    echo Creo il commit con le modifiche rilevate...
    git commit -m "Aggiornamento bot meteo %date% %time%"
) else (
    echo Nessuna nuova modifica da committare.
)

echo.
echo Invio a GitHub in corso...
git push origin main

if %ERRORLEVEL% equ 0 (
    echo.
    echo ===================================================
    echo   [OK] Codice caricato con successo su GitHub!
    echo   Render avviera' automaticamente il redeploy.
    echo ===================================================
) else (
    echo.
    echo ===================================================
    echo   [ATTENZIONE] Si e' verificato un problema con il push.
    echo ===================================================
)

echo.
pause
