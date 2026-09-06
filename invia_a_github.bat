@echo off
chcp 65001 > nul
echo ===================================================
echo   INVIO AGGIORNAMENTI SU GITHUB (PUSH)
echo ===================================================
echo.
cd /d "%~dp0"

echo Verifica e invio commit...
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
    echo   [ATTENZIONE] Si e' verificato un problema.
    echo ===================================================
)

echo.
pause
