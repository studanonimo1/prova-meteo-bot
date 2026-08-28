# 🌦️ Meteo Ensemble Hub - Bot Telegram Cloud 24/7

Guida rapida in **2 minuti** per configurare e mettere online il tuo Bot Telegram su **Render.com** a costo zero, così da poterlo usare direttamente dal tuo smartphone senza tenere acceso il computer.

---

## ⚡ Passo 1: Crea il tuo Bot su Telegram (30 secondi)

1. Apri **Telegram** sul tuo smartphone o PC e cerca **`@BotFather`**.
2. Invia il comando `/newbot`.
3. Inserisci il nome che vuoi dare al bot (es. `Meteo Putignano e Monza`).
4. Inserisci l'username del bot (deve terminare con `bot`, es. `meteo_putignano_monza_bot`).
5. `@BotFather` ti restituirà il tuo **TOKEN API** (es. `123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ`). **Copialo!**

---

## ☁️ Passo 2: Mettilo Online GRATIS 24/7 su Render (Senza PC)

Il repository contiene già tutti i file di configurazione cloud (`render.yaml`, `Dockerfile`, `Procfile` e server health-check su `/health` con keep-alive automatico).

### Procedura di Deploy su Render.com:
1. Crea un account gratuito su [render.com](https://render.com).
2. Carica la cartella `Meteo-Putignano` su un repository GitHub (es. `meteo-telegram-bot`).
3. Su Render, clicca su **New +** e seleziona **Web Service**.
4. Collega il tuo repository GitHub e imposta:
   - **Name:** `meteo-ensemble-bot`
   - **Environment:** `Python`
   - **Region:** `Frankfurt (EU)` (o quella più vicina)
   - **Instance Type:** `Free`
   - **Build Command:** *(lascia vuoto)*
   - **Start Command:** `python meteo_telegram_bot.py`
5. Nella sezione **Environment Variables**, aggiungi:
   - `TELEGRAM_BOT_TOKEN` = *incolla il token di BotFather*
   - `RENDER_EXTERNAL_URL` = *l'URL pubblico fornito da Render (es. `https://meteo-ensemble-bot.onrender.com`)*
   - `KEEP_ALIVE_INTERVAL` = `540`
6. Clicca **Deploy Web Service**.

> [!TIP]
> **Come funziona l'Anti-Sleep 24/7:**
> I Web Service gratuiti di Render vanno in "sleep" dopo 15 minuti di assenza di traffico HTTP. Il bot ha un **Keep-Alive Pinger integrato** che invia automaticamente una richiesta ogni 9 minuti al proprio endpoint `/health`.
> Per una garanzia al 100%, puoi anche aggiungere un monitor gratuito su [UptimeRobot.com](https://uptimerobot.com) o [cron-job.org](https://cron-job.org) impostando una chiamata HTTP GET ogni 5 minuti verso `https://TUO-SERVIZIO.onrender.com/health`.

---

## 📱 Utilizzo su Smartphone

Una volta avviato sul cloud, apri la chat su Telegram dal tuo cellulare:
* **Pulsanti Touch:**
  - `[📍 Putignano]`: Previsioni 3 giorni per Putignano con confronto modelli, piogge e Bulbo Umido.
  - `[📍 Monza]`: Previsioni 3 giorni per Monza con dettaglio orario e afa.
  - `[📡 Sinottico]`: Editoriale specialistico comparato Nord vs Sud.
  - `[🌧️ Solo Pioggia]`: Filtra la vista mostrando unicamente le ore con precipitazioni.
  - `[🔄 Aggiorna Live]`: Ricarica i modelli in tempo reale ignorando la cache.
* **Comandi Rapidi:** `/start`, `/putignano`, `/monza`, `/sinottico`, `/pioggia`, `/help`.
