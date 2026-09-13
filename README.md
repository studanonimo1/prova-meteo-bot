# 🌦️ Meteo Ensemble Hub & Telegram Bot Cloud 24/7

Sistema meteorologico autonomo ad altissima precisione con architettura **Multi-Modello (Ensemble fino a 10 modelli)** e doppio motore:
1. **Bot Telegram Cloud 24/7 Standalone (`meteo_telegram_bot.py`)**: con server HTTP integrato (dashboard e healthcheck per Render/Railway), ricerca città globale, geocoding GPS, monitor allerta pioggia e bollettini avanzati.
2. **CLI Terminale (`previsioni_pioggia_putignano.py`)**: script standalone per consultazione oraria a colori con analisi termodinamica avanzata.

---

## 🚀 Novità Recenti (V3.0)

- **📝 Bollettino Previsioni a 3 Giorni in Stile CML (Centro Meteo Lombardo):**
  - Formattazione descrittiva specialistica pulita (senza emoji invasive, solo marcatore `➡`).
  - Scomposizione in fasce orarie (mattino, pomeriggio, sera) con indicazione **esplicita delle finestre orarie di pioggia** (es. *piogge attese tra le 14:00 e le 18:00 (accumulo 1.8 mm)*) o certificazione di assenza precipitazioni.
  - Temperature minime/massime espresse con range multi-modello e trend rispetto al giorno precedente.
  - Footer con conteggio dinamico esatto dei modelli usati per la media (es. `media 10 modelli`).

- **📡 Editoriale Meteorologico Sinottico Discorsivo (Stile Twitter/X Specialistico):**
  - Ispirato agli editoriali dei meteorologi divulgatori (stile Marco M.M. e Daniele Vasilevski).
  - Testo approfondito (~300-400 parole) articolato in 4 paragrafi fluidi focalizzati sulla città selezionata:
    1. *Titolo giornalistico ad effetto.*
    2. *Inquadramento macro europeo/mediterraneo (promontorio subtropicale, saccature, palude barica).*
    3. *Ricaduta locale al suolo (temperature, bulbo umido/afa, ventilazione e fattore notte/astronomico).*
    4. *Segnale precipitazioni e stabilità troposferica.*
    5. *Spaghetti ensemble multi-modello con spread termico e tendenza.*

---

## 🔬 Modelli Meteorologici Inclusi nell'Ensemble

Il sistema aggrega in tempo reale i principali centri di calcolo mondiali e regionali:

1. **ECMWF IFS (0.25°)** - *Centro Europeo per le Previsioni a Medio Termine (Standard mondiale di riferimento)*
2. **DWD ICON-EU & ICON** - *Servizio Meteorologico Nazionale Tedesco (Alta risoluzione europea e globale)*
3. **Météo-France Seamless & ARPEGE** - *Servizio Meteorologico Nazionale Francese*
4. **GFS Global** - *National Oceanic and Atmospheric Administration (NOAA - USA)*
5. **JMA Seamless** - *Agenzia Meteorologica del Giappone*
6. **GEM Seamless** - *Servizio Meteorologico Canadese*
7. **CMA Grapes** - *Amministrazione Meteorologica Cinese*
8. **BOM Access** - *Ufficio Meteorologico Australiano*

### 🛡️ Architettura Resiliente Anti-Blocco Cloud (Ensemble a 5 o 6 Modelli Sempre Attivo)
- **Sorgente Primaria:** Open-Meteo Ensemble con intestazioni browser standard per superare i blocchi WAF Cloudflare sui server cloud (Render.com) aggregando 5 modelli essenziali (o 10 con API Key).
- **Fallback Ibrido Multi-Dominio a 3–7 Modelli (100% Free, Zero Chiavi):** Se l'endpoint Open-Meteo restituisce HTTP 429 su datacenter condivisi (es. Render.com), il bot attiva un motore parallelo multithread che interroga fornitori istituzionali su domini indipendenti:
  1. **MET Norway (UE)** - *api.met.no* (ECMWF IFS / Arome Norvegia)
  2. **DWD ICON (DE)** - *api.brightsky.dev* (Deutscher Wetterdienst Germania)
  3. **NOAA GFS (USA)** - *www.7timer.info* (National Oceanic and Atmospheric Administration USA)
  4. Centri dedicati Open-Meteo aggiuntivi (Météo-France, CMC GEM, JMA) quando raggiungibili.
- **Tripla Ridondanza Garantita su Render:** Anche nel caso in cui l'intero dominio `open-meteo.com` sia bloccato a livello di IP, il bot aggrega SEMPRE almeno **3 centri di calcolo internazionali** (UE, DE, USA), garantendo la media multi-modello senza alcuna chiave o configurazione.
- **Supporto Opzionale API Key:** Impostando la variabile d'ambiente `OPEN_METEO_API_KEY` su Render, il bot interroga l'endpoint dedicato `customer-api.open-meteo.com` a 10 modelli completi senza limiti di IP.
- **Cache Dinamica:** 15 minuti su ensemble completo Open-Meteo, 4 minuti in modalità fallback per riagganciare automaticamente la sorgente primaria appena l'IP si sblocca.
- **Comando Diagnostica Live:** `/diagnostica` (o `/status`, `/debug`) su Telegram mostra lo stato di salute dei centri di calcolo, codici HTTP e memoria cache.

---

## 📱 Bot Telegram Standalone (`meteo_telegram_bot.py`)

### Funzionalità Principali
- **Ricerca Globale:** Digita qualsiasi città (es. `Roma`, `Milano`, `Bari`, `New York`) o usa `/citta <nome>`.
- **Posizione GPS in Tempo Reale:** Invia la posizione GPS direttamente tramite la graffetta 📎 di Telegram.
- **Coordinate Dirette:** Supporto coordinate numeriche (es. `/coord 45.56 9.23`).
- **Allerta Pioggia Multi-Punto:** Monitoraggio in background ogni 30 minuti su 2 località personalizzabili (`/alert_punto1`, `/alert_punto2`, `/alert_on`, `/alert_off`).
- **Schede Interattive Inline:**
  - `[ 🌡️ Adesso ]`: Condizione live, bulbo umido (Stull), vento e trend 3 ore.
  - `[ ☀️ Sole & Crepuscolo ]`: Quadro astronomico NOAA (alba, tramonto, crepuscolo civile, mezzogiorno solare).
  - `[ 📅 Previsioni 3gg ]`: Bollettino descrittivo stile CML con orari pioggia e min/max.
  - `[ 📡 Sinottico ]`: Editoriale meteorologico divulgativo avanzato.
  - `[ 🌧️ Solo Pioggia ]`: Filtro esclusivo sulle ore piovose.

---

## 💻 Utilizzo da Terminale (CLI Locale)

Esegui il batch interattivo:
```powershell
py avvia_previsioni.bat
```
Oppure direttamente da riga di comando:
```powershell
# Previsioni per Monza
py previsioni_pioggia_putignano.py --citta monza

# Previsioni per Putignano
py previsioni_pioggia_putignano.py --citta putignano

# Filtra solo le ore di pioggia
py previsioni_pioggia_putignano.py --citta monza --solo-pioggia

# Estendi la previsione fino a 5 o 7 giorni
py previsioni_pioggia_putignano.py --citta monza --giorni 5
```

---

## 🧪 Smoke Test e Validazione Automatica
 
Il repository include una suite di collaudo automatico locale:
```powershell
# Validazione bollettino CML 3gg ed editoriale sinottico
py test_cml_bulletin.py

# Validazione fallback ibrido 6 modelli e resilienza 429
py test_hybrid_fallback.py
```
Verifica istantaneamente:
- Conformità del bollettino 3gg in stile CML (assenza emoji, presenza finestre pioggia e min/max).
- Conformità dell'editoriale sinottico (stile discorsivo, conteggio parole > 200, aderenza alla città).
- Attivazione e correttezza dell'ensemble ibrido a 6 modelli anche con blocco HTTP 429.
