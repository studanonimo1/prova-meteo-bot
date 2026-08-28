@echo off
title Meteo Ensemble Telegram Bot
echo ===================================================
echo  🌦️ Meteo Multi-Modello - Avvio Bot Telegram
echo ===================================================
where py >nul 2>nul
if %errorlevel% equ 0 (
    py meteo_telegram_bot.py
) else (
    python meteo_telegram_bot.py
)
pause
