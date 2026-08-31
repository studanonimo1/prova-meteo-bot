# 🌦️ Meteo Ensemble Hub - Bot Telegram Cloud 24/7

Guida rapida per configurare e usare il tuo Bot Telegram su **Render.com** (o locale) con previsioni multi-modello, ricerca città globale, invio posizione GPS, monitor di allerta pioggia automatico e **mappe grafiche meteo ad alto contrasto**.

---

## ⚡ Passo 1: Crea il tuo Bot su Telegram (30 secondi)

1. Apri **Telegram** sul tuo smartphone o PC e cerca **`@BotFather`**.
2. Invia il comando `/newbot`.
3. Inserisci il nome che vuoi dare al bot (es. `Meteo Ensemble Bot`).
4. Inserisci l'username del bot (deve terminare con `bot`, es. `mio_meteo_ensemble_bot`).
5. `@BotFather` ti restituirà il tuo **TOKEN API** (es. `123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ`). **Copialo!**

---

## ☁️ Passo 2: Deploy Gratuito 24/7 su Render (Senza PC)

1. Crea un account su [render.com](https://render.com).
2. Carica i file di `Meteo-Putignano` su GitHub.
3. Su Render, crea un **New Web Service**:
   - **Environment:** `Python`
   - **Start Command:** `python meteo_telegram_bot.py`
   - **Instance Type:** `Free`
4. Nella sezione **Environment Variables**, aggiungi:
   - `TELEGRAM_BOT_TOKEN`: *Il token di BotFather*
   - `RENDER_EXTERNAL_URL`: *L'URL pubblico fornito da Render (es. `https://meteo-ensemble-bot.onrender.com`)*
   - `KEEP_ALIVE_INTERVAL`: `540`
5. Clicca **Deploy Web Service**.

---

## 📱 Guida alle Funzionalità

### 🗺️ 1. Mappe Meteo Statica PNG ad Alto Contrasto
* **Pulsante dedicato:** Tocca **`[ 🗺️ Mappa ]`** nella tastiera Telegram per ricevere all'istante l'immagine satellitare/stradale centrate sulla tua città.
* **Comando Mappa:** Invia `/mappa` (per la località attiva) o `/mappa <nome città / coordinate>` (es. `/mappa Roma` o `/mappa 40.85 17.12`).
* **Cosa include l'immagine generata con Pillow:**
  - Mappa geografica locale ad alta definizione (raggio ~30 km).
  - Pin GPS e radar circolare con coordinate esatte.
  - Cartellino **Temperatura Attuale (°C)** e condizioni meteorologiche.
  - Cartellino **Precipitazioni 24h**: probabilità cumulata (%), stima millimetri (mm) e badge di rischio (Basso / Moderato / Allerta).

### 🔍 2. Ricerca Qualsiasi Città & Posizione GPS
* **Ricerca per Nome:** Scrivi semplicemente il nome di qualsiasi città in chat (es. `Roma`, `Bari`, `Milano`, `Londra`) oppure usa `/citta Firenze`.
* **Invio Posizione GPS da Telefono:** Tocca la graffetta 📎 nella chat di Telegram -> seleziona **Posizione**: il bot calcolerà all'istante il meteo per il punto esatto in cui ti trovi!
* **Coordinate Numeriche:** Invia latitudine e longitudine separate da virgola o spazio (es. `40.8505, 17.1235` o `/coord 45.56 9.24`).

### 🔔 3. Allerta Pioggia Imminente su 2 Punti di Interesse
Il bot include un **monitor in background** che controlla ogni 30 minuti l'arrivo di piogge imminenti:
* `/alert_on` - Attiva gli avvisi automatici (ti invia un messaggio se la pioggia è prevista entro 2-3 ore).
* `/alert_off` - Disattiva gli avvisi.
* `/alert_punto1 <città o coord>` - Imposta il **Punto 1** di allerta (es. `/alert_punto1 Putignano`).
* `/alert_punto2 <città o coord>` - Imposta il **Punto 2** di allerta (es. `/alert_punto2 Monza` o `/alert_punto2 45.56, 9.24`).
* `/alert_status` - Mostra lo stato e i punti attualmente monitorati.

### 🎛️ 4. Navigazione & Schede Interattive
* `[ 📍 Putignano ]` / `[ 📍 Monza ]` / `[ 📍 Città Attiva ]`
* `[ 🌡️ Adesso ]`: Temperatura live calcolata su orario locale italiano esatto, Bulbo Umido, vento e trend 3 ore.
* `[ 📅 Previsioni 3gg ]`: Riepilogo giornaliero con confronto modelli e cumulati.
* `[ 📡 Sinottico ]`: Editoriale meteorologico specialistico mirato per la località selezionata.
* `[ 🗺️ Mappa ]`: Generazione mappa PNG con dati in sovrimpressione.
* `[ 🌧️ Solo Pioggia ]`: Filtra le sole fasce orarie con precipitazioni.
* `[ 🔔 Alert Pioggia: ON/OFF ]`: Attiva o spegne le notifiche push direttamente con un tocco.
