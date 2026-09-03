# 🌦️ Meteo Ensemble Hub - Bot Telegram Cloud 24/7

Guida rapida per configurare e usare il tuo Bot Telegram su **Render.com** (o in locale) con previsioni multi-modello, ricerca città globale, invio posizione GPS, monitor di allerta pioggia automatico multi-punto e **doppia sorgente dati resiliente anti-blocco IP (Open-Meteo Ensemble + MET Norway)** a zero dipendenze esterne.

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

## 🛡️ Doppia Sorgente Resiliente Anti-Blocco Cloud (Open-Meteo + MET Norway)

Sui servizi cloud gratuiti come Render, l'indirizzo IP di uscita è condiviso con migliaia di altri utenti e può capitare che Open-Meteo restituisca temporaneamente l'errore `HTTP 429 Too Many Requests` per colpa di altro traffico nel datacenter.

Il bot risolve questo problema in modo completamente trasparente:
1. **Sorgente Primaria:** Open-Meteo Multi-Modello (*ECMWF, ICON, M-France, GFS, JMA*).
2. **Sorgente di Riserva Istantanea (MET Norway Locationforecast 2.0):** Se Open-Meteo è limitato o irraggiungibile, il bot interroga all'istante i supercomputer meteorologici dell'Istituto Meteorologico Norvegese (servizio pubblico europeo, 100% gratuito e senza rate-limit).
3. **Nessun messaggio di errore o avvisi invasivi:** I messaggi mostrano sempre in modo pulito e immediato l'orario effettivo di rilevamento.

---

## 📱 Guida ai Comandi e Funzionalità

### 🔍 1. Ricerca Qualsiasi Città & Posizione GPS
* **Ricerca per Nome:** Scrivi semplicemente il nome di qualsiasi città in chat (es. `Roma`, `Bari`, `Milano`, `Napoli`) oppure usa `/citta Firenze`.
* **Invio Posizione GPS da Telefono:** Tocca la graffetta 📎 nella chat di Telegram -> seleziona **Posizione**: il bot calcolerà all'istante il meteo per le coordinate esatte in cui ti trovi!
* **Coordinate Numeriche:** Invia latitudine e longitudine separate da virgola o spazio (es. `40.8505, 17.1235` o `/coord 45.56 9.24`).

### 🔔 2. Allerta Pioggia Imminente su 2 Punti di Interesse
Il bot include un **monitor in background** che controlla ogni 30 minuti l'arrivo di piogge imminenti:
* `/alert_on` - Attiva gli avvisi automatici (ti invia un messaggio se la pioggia è prevista entro 2-3 ore).
* `/alert_off` - Disattiva gli avvisi.
* `/alert_punto1 <città o coord>` - Imposta il **Punto 1** di allerta (es. `/alert_punto1 Putignano`).
* `/alert_punto2 <città o coord>` - Imposta il **Punto 2** di allerta (es. `/alert_punto2 Monza` o `/alert_punto2 45.56, 9.24`).
* `/alert_status` - Mostra lo stato e i punti attualmente monitorati.

### 🎛️ 3. Navigazione & Schede Interattive
* `[ 📍 Putignano ]` / `[ 📍 Monza ]` / `[ 📍 Città Attiva ]`
* `[ 🌡️ Adesso ]`: Temperatura live calcolata su orario locale italiano esatto, Bulbo Umido, umidità, vento e trend 3 ore.
* `[ 📅 Previsioni 3gg ]`: Riepilogo giornaliero con confronto modelli e cumulati di pioggia.
* `[ 📡 Sinottico ]`: Editoriale meteorologico specialistico mirato per la località selezionata.
* `[ 🌧️ Solo Pioggia ]`: Filtra le sole fasce orarie con precipitazioni.
* `[ 🔔 Alert Pioggia: ON/OFF ]`: Attiva o spegne le notifiche push direttamente con un tocco.
