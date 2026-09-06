# Previsioni Meteo & Pioggia Multi-Modello - Putignano (BA) & Monza

Script Python autonomo ad altissima precisione che calcola e visualizza a terminale le previsioni meteorologiche orarie per **Putignano (BA)** e **Monza** (coordinate esatte: `45.566708, 9.239812`) sui prossimi 3 giorni, aggregando e confrontando **5 tra i migliori modelli meteorologici al mondo**:

1. **ECMWF IFS (0.25°)** - *Centro Europeo per le Previsioni a Medio Termine* (Standard mondiale di riferimento)
2. **DWD ICON-EU** - *Servizio Meteorologico Nazionale Tedesco* (Modello europeo ad alta risoluzione)
3. **Météo-France Seamless** - *Servizio Meteorologico Francese*
4. **GFS Global** - *National Oceanic and Atmospheric Administration (NOAA - USA)*
5. **JMA Seamless** - *Agenzia Meteorologica del Giappone*

---

## 🌟 Località Supportate

- **Putignano (BA):** Lat 40.8505°N, Lon 17.1235°E
- **Monza:** Lat 45.566708°N, Lon 9.239812°E (Via Valosa di Sopra 23)

---

## 🌟 Parametri Inclusi

- ☀️ **Condizione Cielo & Icona WMO** (Sereno, Parz. Nuvoloso, Pioggia debole/forte, Temporale, ecc.)
- 🌡️ **Temperatura Reale (°C)**
- 💧 **Temperatura di Bulbo Umido (Wet Bulb °C)** calcolata con la formula di Stull (2011) per la valutazione del comfort termico e dello stress da calore
- 🌧️ **Precipitazioni Orarie (mm)** e **Probabilità (%)** con media ensemble e range min-max
- 💨 **Vento** (Velocità in km/h e direzione cardinale N, NE, E, SE, S, SW, W, NW)
- 💧 **Umidità Relativa (%)**
- 📊 **Riepilogo Giornaliero Integrato** con confronto accumuli fra i 5 modelli e finestre di allerta pioggia

---

## 🚀 Come Eseguire

### 1. Avvio Rapido con Menu Interattivo
Fai doppio click su `avvia_previsioni.bat` oppure esegui:
```powershell
py previsioni_pioggia_putignano.py
```
Ti verrà mostrato un menu dove digitare `1` per Putignano, `2` per Monza, o `3` per entrambe le città.

### 2. Avvio Diretto da Terminale (CLI)
- **Solo per Monza:**
  ```powershell
  py previsioni_pioggia_putignano.py --citta monza
  ```
- **Solo per Putignano:**
  ```powershell
  py previsioni_pioggia_putignano.py --citta putignano
  ```
- **Entrambe le città:**
  ```powershell
  py previsioni_pioggia_putignano.py --citta entrambe
  ```
- **Filtra solo le ore di pioggia:**
  ```powershell
  py previsioni_pioggia_putignano.py --citta monza --solo-pioggia
  ```
- **Estendi la previsione fino a 7 giorni:**
  ```powershell
  py previsioni_pioggia_putignano.py --citta monza --giorni 5
  ```
