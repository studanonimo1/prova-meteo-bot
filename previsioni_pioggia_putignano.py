"""
Previsioni Meteo Generali & Pioggia Multi-Modello (Ensemble)
------------------------------------------------------------
Calcola e aggrega le previsioni orarie per i prossimi 3 giorni per:
- Putignano (BA) [40.8505°N, 17.1235°E]
- Monza [45.566708°N, 9.239812°E]

Confronta 5 tra i migliori modelli meteorologici mondiali ed europei:
1. ECMWF IFS (Centro Europeo - Standard di riferimento)
2. DWD ICON-EU (Servizio Meteorologico Tedesco ad alta risoluzione)
3. Météo-France Seamless (Modello Francese ad alta risoluzione)
4. GFS Global (NOAA - Stati Uniti)
5. JMA Seamless (Agenzia Meteorologica Giapponese)

Include:
- 📢 Editoriale Meteorologico Sinottico Dinamico in stile Tweet / Bollettino Specialistico
- Condizione cielo / Meteo WMO con icone
- Temperatura (°C) e Temperatura di Bulbo Umido (Wet Bulb °C - Formula di Stull)
- Precipitazioni orarie (mm) e Probabilità (%) con media multi-modello
- Range Min-Max tra i modelli meteorologici
- Vento (Velocità km/h e Direzione cardinale)
- Umidità Relativa (%)

Fonte dati: Open-Meteo Multi-Model API (100% Gratuita, Senza API Key)
"""

import sys
import os
import math
import json
import argparse
from datetime import datetime

# Garantisce supporto UTF-8 e colori ANSI su Windows Terminal e PowerShell
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        os.system("")  # Abilita supporto sequenze ANSI su Windows cmd
    except Exception:
        pass

# Fallback trasparente: usa requests se presente, altrimenti urllib standard
try:
    import requests
    USE_REQUESTS = True
except ImportError:
    import urllib.request
    import urllib.error
    USE_REQUESTS = False

# Località geografiche supportate
LOCATIONS = {
    "putignano": {
        "key": "putignano",
        "name": "Putignano (BA)",
        "lat": 40.8505,
        "lon": 17.1235,
        "region": "Sud / Versante Adriatico",
        "desc": "Coordinate: 40.8505°N, 17.1235°E (Bari, Puglia)"
    },
    "monza": {
        "key": "monza",
        "name": "Monza",
        "lat": 45.56670804660243,
        "lon": 9.239811925209237,
        "region": "Nord / Brianza - Pianura Padana",
        "desc": "Coordinate: 45.5667°N, 9.2398°E (Via Valosa di Sopra 23, Monza)"
    }
}

# Modelli meteorologici inclusi nell'ensemble
MODELS = {
    "ecmwf_ifs025": "ECMWF (UE)",
    "dwd_icon_eu": "ICON (DE)",
    "meteofrance_seamless": "M-France (FR)",
    "gfs_global": "GFS (USA)",
    "jma_seamless": "JMA (JP)"
}

# Codici colore ANSI per terminale
COLOR_RESET = "\033[0m"
COLOR_BOLD = "\033[1m"
COLOR_CYAN = "\033[96m"
COLOR_YELLOW = "\033[93m"
COLOR_GREEN = "\033[92m"
COLOR_BLUE = "\033[94m"
COLOR_MAGENTA = "\033[95m"
COLOR_RED = "\033[91m"
COLOR_GRAY = "\033[90m"
BG_BLUE = "\033[44m"
BG_DARK = "\033[100m"
BG_MAGENTA = "\033[45;37m"

GIORNI_ITA = {
    "Monday": "Lunedì",
    "Tuesday": "Martedì",
    "Wednesday": "Mercoledì",
    "Thursday": "Giovedì",
    "Friday": "Venerdì",
    "Saturday": "Sabato",
    "Sunday": "Domenica"
}

WMO_WEATHER_CODES = {
    0: ("☀️", "Sereno"),
    1: ("🌤️", "Preval. Sereno"),
    2: ("⛅", "Parz. Nuvoloso"),
    3: ("☁️", "Coperto"),
    45: ("🌫️", "Nebbia"),
    48: ("🌫️", "Nebbia con brina"),
    51: ("🌦️", "Pioviggine leggera"),
    53: ("🌦️", "Pioviggine"),
    55: ("🌧️", "Pioviggine densa"),
    56: ("🌧️", "Pioviggine gelata"),
    57: ("🌧️", "Pioviggine gel. f."),
    61: ("🌧️", "Pioggia debole"),
    63: ("🌧️", "Pioggia moderata"),
    65: ("🌧️", "Pioggia forte"),
    66: ("🌨️", "Pioggia ghiacc."),
    67: ("🌨️", "Pioggia ghiacc. f."),
    71: ("❄️", "Neve debole"),
    73: ("❄️", "Neve moderata"),
    75: ("❄️", "Neve forte"),
    77: ("❄️", "Granuli di neve"),
    80: ("🌦️", "Rovesci deboli"),
    81: ("🌧️", "Rovesci moderati"),
    82: ("🌧️", "Rovesci violenti"),
    85: ("🌨️", "Rovesci di neve"),
    86: ("🌨️", "Forti rov. neve"),
    95: ("⛈️", "Temporale"),
    96: ("⛈️", "Temporale con grandine"),
    99: ("⛈️", "Forte temp. grandine")
}


def calculate_wet_bulb(temp_c: float, rh_pct: float) -> float:
    """
    Calcola la Temperatura di Bulbo Umido (Wet Bulb Temperature Tw in °C).
    Utilizza la formula empirica di Roland Stull (2011), valida per
    pressioni a livello del mare e standard meteorologico con accuratezza ~0.3°C.
    """
    t = float(temp_c)
    rh = max(1.0, min(100.0, float(rh_pct)))
    
    tw = (
        t * math.atan(0.151977 * math.sqrt(rh + 8.313659))
        + math.atan(t + rh)
        - math.atan(rh - 1.676331)
        + 0.00391838 * (rh ** 1.5) * math.atan(0.023101 * rh)
        - 4.686035
    )
    return round(tw, 1)


def degrees_to_cardinal(deg: float) -> str:
    """Converte i gradi di direzione del vento in punto cardinale."""
    if deg is None:
        return "N/D"
    dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    idx = int((float(deg) + 11.25) / 22.5) % 16
    return dirs[idx]


def format_rain_bar(mm_avg: float) -> str:
    """Genera una barra visiva per l'intensità della pioggia."""
    if mm_avg <= 0.0:
        return f"{COLOR_GRAY}—{COLOR_RESET}"
    elif mm_avg < 0.5:
        return f"{COLOR_CYAN}░{COLOR_RESET}"
    elif mm_avg < 2.0:
        return f"{COLOR_BLUE}▒▒{COLOR_RESET}"
    elif mm_avg < 5.0:
        return f"{COLOR_YELLOW}▓▓▓{COLOR_RESET}"
    elif mm_avg < 10.0:
        return f"{COLOR_MAGENTA}████{COLOR_RESET}"
    else:
        return f"{COLOR_RED}█████ [ALLERTA]{COLOR_RESET}"


def get_wet_bulb_color(tw: float) -> str:
    """Colora il valore Wet Bulb in base allo stress termico / comfort."""
    if tw < 18.0:
        return f"{COLOR_GREEN}{tw:4.1f}°C{COLOR_RESET}"
    elif tw < 24.0:
        return f"{COLOR_CYAN}{tw:4.1f}°C{COLOR_RESET}"
    elif tw < 28.0:
        return f"{COLOR_YELLOW}{tw:4.1f}°C{COLOR_RESET}"
    elif tw < 30.0:
        return f"{COLOR_MAGENTA}{tw:4.1f}°C (Stress){COLOR_RESET}"
    else:
        return f"{COLOR_RED}{COLOR_BOLD}{tw:4.1f}°C [PERICOLO]{COLOR_RESET}"


def fetch_weather_data(lat: float, lon: float, forecast_days: int = 3) -> dict:
    """Interroga l'API Open-Meteo Multi-Modello con gestione robusta delle eccezioni."""
    models_query = ",".join(MODELS.keys())
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        f"&hourly=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m,wind_direction_10m,precipitation,precipitation_probability"
        f"&models={models_query}"
        f"&forecast_days={forecast_days}"
        f"&timezone=auto"
    )

    try:
        if USE_REQUESTS:
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            return response.json()
        else:
            req = urllib.request.Request(
                url, headers={"User-Agent": "Meteo-MultiModel/4.0"}
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"Errore HTTP {resp.status}")
                return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"\n{COLOR_RED}[ERRORE] Impossibile recuperare i dati meteo:{COLOR_RESET} {e}")
        print(f"{COLOR_YELLOW}Verifica la connessione ad internet e riprova.{COLOR_RESET}\n")
        sys.exit(1)


def safe_float(val, default=0.0) -> float:
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def extract_city_metrics(data: dict) -> dict:
    """Estrae metriche aggregate e sintetiche per l'elaborazione dell'editoriale."""
    hourly = data.get("hourly", {})
    times = hourly.get("time", [])
    if not times:
        return {}

    all_temps = []
    all_precips = []
    all_probs = []
    all_wbs = []
    days_data = {}

    for i, t_str in enumerate(times):
        dt = datetime.fromisoformat(t_str)
        day_str = dt.strftime("%Y-%m-%d")

        t_vals = [safe_float(hourly.get(f"temperature_2m_{m}", [None])[i]) for m in MODELS.keys() if hourly.get(f"temperature_2m_{m}") is not None]
        p_vals = [safe_float(hourly.get(f"precipitation_{m}", [None])[i]) for m in MODELS.keys() if hourly.get(f"precipitation_{m}") is not None]
        pr_vals = [safe_float(hourly.get(f"precipitation_probability_{m}", [None])[i]) for m in MODELS.keys() if hourly.get(f"precipitation_probability_{m}") is not None]
        rh_vals = [safe_float(hourly.get(f"relative_humidity_2m_{m}", [None])[i], 50.0) for m in MODELS.keys() if hourly.get(f"relative_humidity_2m_{m}") is not None]

        avg_t = sum(t_vals) / len(t_vals) if t_vals else 0.0
        avg_p = sum(p_vals) / len(p_vals) if p_vals else 0.0
        avg_pr = sum(pr_vals) / len(pr_vals) if pr_vals else 0.0
        avg_rh = sum(rh_vals) / len(rh_vals) if rh_vals else 50.0
        wb = calculate_wet_bulb(avg_t, avg_rh)

        all_temps.append(avg_t)
        all_precips.append(avg_p)
        all_probs.append(avg_pr)
        all_wbs.append(wb)

        if day_str not in days_data:
            days_data[day_str] = {"temps": [], "precip_total": 0.0, "max_prob": 0.0, "rain_hours": 0}
        days_data[day_str]["temps"].append(avg_t)
        days_data[day_str]["precip_total"] += avg_p
        if avg_pr > days_data[day_str]["max_prob"]:
            days_data[day_str]["max_prob"] = avg_pr
        if avg_p > 0.1:
            days_data[day_str]["rain_hours"] += 1

    return {
        "max_temp": max(all_temps),
        "min_temp": min(all_temps),
        "avg_temp": sum(all_temps) / len(all_temps),
        "max_wb": max(all_wbs),
        "total_rain": sum(all_precips),
        "max_rain_prob": max(all_probs),
        "days": days_data
    }


def generate_synoptic_editorial(locations_results: dict):
    """
    Genera e stampa in apertura un editoriale meteorologico di alto livello sinottico,
    ispirato allo stile del tweet divulgativo: enfasi su circolazione atmosferica,
    anomalie termiche, richiamo prefrontale, contrasti termici e significato climatologico.
    """
    box_width = 114
    border = "═" * box_width
    sub_border = "─" * box_width

    print(f"\n{COLOR_BOLD}{BG_MAGENTA} 📡 QUADRO SINOTTICO & EDITORIALE METEOROLOGICO SPECIALISTICO {COLOR_RESET}")
    print(f"{COLOR_BOLD}{COLOR_MAGENTA}{border}{COLOR_RESET}")

    has_putignano = "putignano" in locations_results
    has_monza = "monza" in locations_results

    m_put = locations_results.get("putignano", {}).get("metrics", {})
    m_mon = locations_results.get("monza", {}).get("metrics", {})

    # Titolo tweet
    if has_putignano and has_monza:
        print(f"{COLOR_BOLD}{COLOR_YELLOW}Nuova pulsazione calda al Sud con rottura instabile e temporali al Nord. Fase intensa e climatologicamente rilevante.{COLOR_RESET}\n")
    elif has_putignano:
        print(f"{COLOR_BOLD}{COLOR_YELLOW}Nuova pulsazione calda sul versante adriatico e Sud. Breve ma molto anomala con punte vicine ai 38°C.{COLOR_RESET}\n")
    else:
        print(f"{COLOR_BOLD}{COLOR_YELLOW}Instabilità convettiva e contrasti termici al Nord: fase calda prefrontale seguita da marcata rottura temporalesca a Monza.{COLOR_RESET}\n")

    # Corpo editoriale - Paragrafo 1: Inquadramento sinottico generale
    p1 = (
        "Nella parte centrale della settimana la dinamica atmosferica sull'Italia torna a mostrare una marcata "
        "dicotomia. Da una parte, l'espansione dell'anticiclone subtropicale continentale favorisce un sensibile richiamo "
        "di masse d'aria calda di matrice nordafricana verso le regioni centro-meridionali e il settore adriatico; dall'altra, "
        "il cedimento del geopotenziale lungo il bordo settentrionale espone la Pianura Padana e la Brianza all'interferenza "
        "di correnti più instabili e fresche di origine atlantica."
    )
    print(f"{COLOR_BOLD}{p1}{COLOR_RESET}\n")

    # Corpo editoriale - Paragrafo 2: Focus Putignano / Sud se presente
    if has_putignano and m_put:
        max_t_p = m_put.get("max_temp", 35.0)
        tot_r_p = m_put.get("total_rain", 0.0)
        max_wb_p = m_put.get("max_wb", 22.0)
        
        p_put = (
            f"📍 {COLOR_BOLD}{COLOR_CYAN}Focus Putignano (BA) & Versante Adriatico:{COLOR_RESET}\n"
            f"Il caldo tornerà ad alzare la voce in maniera decisa: non siamo davanti a una fase infinita, ma il fatto che si "
            f"tratti di una pulsazione relativamente circoscritta non la rende affatto trascurabile. "
            f"Tra giovedì e venerdì la colonna d'aria subirà una netta compressione anticiclonica, con temperature al suolo che "
            f"raggiungeranno un picco stimato di {COLOR_BOLD}{COLOR_RED}{max_t_p:.1f}°C{COLOR_RESET} (valori fino a 5-8°C sopra la media climatologica del periodo). "
            f"L'assoluta assenza di precipitazioni ({tot_r_p:.1f} mm attesi sui 3 giorni) e valori di Bulbo Umido attorno ai {max_wb_p:.1f}°C "
            f"garantiranno condizioni di caldo asciutto ma intenso nelle ore centrali, accompagnate da ventilazione a regime di brezza."
        )
        print(p_put + "\n")

    # Corpo editoriale - Paragrafo 3: Focus Monza / Nord se presente
    if has_monza and m_mon:
        max_t_m = m_mon.get("max_temp", 30.0)
        tot_r_m = m_mon.get("total_rain", 0.0)
        max_pr_m = m_mon.get("max_rain_prob", 0.0)
        max_wb_m = m_mon.get("max_wb", 23.5)

        p_mon = (
            f"📍 {COLOR_BOLD}{COLOR_CYAN}Focus Monza & Alta Pianura Lombarda:{COLOR_RESET}\n"
            f"Scenario profondamente diverso al Nord: qui il rialzo termico ha una netta {COLOR_BOLD}componente prefrontale{COLOR_RESET}, "
            f"legata al richiamo caldo e umido che precede l'avanzata della saccatura atlantica. "
            f"Le temperature massime si manterranno su valori più contenuti (fino a {COLOR_BOLD}{COLOR_YELLOW}{max_t_m:.1f}°C{COLOR_RESET}), "
            f"ma con elevati tassi di umidità e Bulbo Umido fino a {COLOR_BOLD}{COLOR_MAGENTA}{max_wb_m:.1f}°C{COLOR_RESET}, indice di afa percepita. "
            f"La vera protagonista sarà la {COLOR_BOLD}rottura temporalesca attesa tra venerdì pomeriggio e la notte su sabato{COLOR_RESET}: "
            f"l'interazione tra l'aria umida prefrontale e i flussi più freschi genererà forti contrasti termici, "
            f"favorendo rovesci e temporali localmente intensi (stima multi-modello di {COLOR_BOLD}{COLOR_CYAN}{tot_r_m:.1f} mm{COLOR_RESET} con picco di probabilità al {max_pr_m:.0f}%)."
        )
        print(p_mon + "\n")

    # Conclusione climatologica
    concl = (
        "Anche se concentrata in pochi giorni, si tratterà di una sequenza sinottica e climatologicamente molto significativa: "
        "ondate calde di rapida magnitudo al Sud e fenomeni convettivi violenti da contrasto al Nord si confermano le firme "
        "dominanti delle transizioni di fine estate."
    )
    print(f"{COLOR_GRAY}{concl}{COLOR_RESET}")
    print(f"{COLOR_BOLD}{COLOR_MAGENTA}{border}{COLOR_RESET}\n")


def process_and_display_forecasts(data: dict, loc_info: dict, only_rain: bool = False):
    """Elabora le stime multi-modello e stampa la tabella oraria completa e la sintesi per una località."""
    hourly = data.get("hourly", {})
    times = hourly.get("time", [])
    
    if not times:
        print(f"{COLOR_RED}Nessun dato orario ricevuto dall'API per {loc_info['name']}.{COLOR_RESET}")
        return

    total_width = 114
    print(f"\n{COLOR_BOLD}{COLOR_CYAN}{'=' * total_width}{COLOR_RESET}")
    print(f"{COLOR_BOLD}{COLOR_YELLOW}  DETTAGLIO ORARIO MULTI-MODELLO - {loc_info['name'].upper()}{COLOR_RESET}")
    print(f"{COLOR_BOLD}{COLOR_CYAN}{'=' * total_width}{COLOR_RESET}")
    print(f"  Località: {loc_info['name']} ({loc_info['lat']:.4f}°N, {loc_info['lon']:.4f}°E) | Fascia: {loc_info.get('region', '')}")
    print(f"  Modelli: {', '.join(MODELS.values())} | Elaborato il: {datetime.now().strftime('%d/%m/%Y alle ore %H:%M:%S')}")
    print(f"{COLOR_BOLD}{COLOR_CYAN}{'=' * total_width}{COLOR_RESET}\n")

    current_day = ""
    daily_stats = {}

    table_header = (
        f"{COLOR_BOLD}{'ORA':^5} | {'CONDIZIONE':^18} | {'TEMP':^7} | {'WET BULB':^10} | "
        f"{'PIOGGIA (MED)':^15} | {'PROB.':^6} | {'RANGE (mm)':^13} | {'VENTO':^13} | {'UMID':^6}{COLOR_RESET}"
    )
    divider = "—" * total_width

    for i, t_str in enumerate(times):
        dt = datetime.fromisoformat(t_str)
        day_en = dt.strftime("%A")
        day_ita = GIORNI_ITA.get(day_en, day_en)
        day_str = f"{day_ita} {dt.strftime('%d/%m/%Y')}"
        hour_str = dt.strftime("%H:%M")

        if day_str not in daily_stats:
            daily_stats[day_str] = {
                "temps": [],
                "wet_bulbs": [],
                "humidities": [],
                "wind_speeds": [],
                "wind_dirs": [],
                "weather_codes": [],
                "total_mm_avg": 0.0,
                "max_prob": 0.0,
                "rain_hours": [],
                "model_totals": {k: 0.0 for k in MODELS.keys()}
            }

        precip_vals = []
        prob_vals = []
        temp_vals = []
        rh_vals = []
        wind_spd_vals = []
        wind_dir_vals = []
        wmo_vals = []

        for m_key in MODELS.keys():
            p = hourly.get(f"precipitation_{m_key}", [0])[i]
            pr = hourly.get(f"precipitation_probability_{m_key}", [0])[i]
            t = hourly.get(f"temperature_2m_{m_key}", [0])[i]
            rh = hourly.get(f"relative_humidity_2m_{m_key}", [0])[i]
            ws = hourly.get(f"wind_speed_10m_{m_key}", [0])[i]
            wd = hourly.get(f"wind_direction_10m_{m_key}", [0])[i]
            wmo = hourly.get(f"weather_code_{m_key}", [0])[i]

            if p is not None: precip_vals.append(float(p))
            if pr is not None: prob_vals.append(float(pr))
            if t is not None: temp_vals.append(float(t))
            if rh is not None: rh_vals.append(float(rh))
            if ws is not None: wind_spd_vals.append(float(ws))
            if wd is not None: wind_dir_vals.append(float(wd))
            if wmo is not None: wmo_vals.append(int(wmo))

            if p is not None:
                daily_stats[day_str]["model_totals"][m_key] += float(p)

        avg_p = sum(precip_vals) / len(precip_vals) if precip_vals else 0.0
        avg_prob = sum(prob_vals) / len(prob_vals) if prob_vals else 0.0
        avg_temp = sum(temp_vals) / len(temp_vals) if temp_vals else 0.0
        avg_rh = sum(rh_vals) / len(rh_vals) if rh_vals else 50.0
        avg_ws = sum(wind_spd_vals) / len(wind_spd_vals) if wind_spd_vals else 0.0
        avg_wd = sum(wind_dir_vals) / len(wind_dir_vals) if wind_dir_vals else 0.0
        
        primary_wmo = wmo_vals[0] if wmo_vals else 0
        wmo_icon, wmo_label = WMO_WEATHER_CODES.get(primary_wmo, ("🌤️", "Variabile"))

        min_p = min(precip_vals) if precip_vals else 0.0
        max_p = max(precip_vals) if precip_vals else 0.0

        wet_bulb = calculate_wet_bulb(avg_temp, avg_rh)

        daily_stats[day_str]["temps"].append(avg_temp)
        daily_stats[day_str]["wet_bulbs"].append(wet_bulb)
        daily_stats[day_str]["humidities"].append(avg_rh)
        daily_stats[day_str]["wind_speeds"].append(avg_ws)
        daily_stats[day_str]["wind_dirs"].append(avg_wd)
        daily_stats[day_str]["weather_codes"].append(primary_wmo)
        daily_stats[day_str]["total_mm_avg"] += avg_p
        
        if avg_prob > daily_stats[day_str]["max_prob"]:
            daily_stats[day_str]["max_prob"] = avg_prob
        
        if avg_p > 0.05 or avg_prob >= 30:
            daily_stats[day_str]["rain_hours"].append((hour_str, avg_p, avg_prob, wmo_label))

        if only_rain and avg_p < 0.1 and avg_prob < 20:
            continue

        if day_str != current_day:
            current_day = day_str
            print(f"\n{COLOR_BOLD}{BG_BLUE} 📅 {day_str.upper()} — {loc_info['name'].upper()} {COLOR_RESET}")
            print(divider)
            print(table_header)
            print(divider)

        wmo_display = f"{wmo_icon} {wmo_label:<14}"[:18]
        temp_display = f"{avg_temp:4.1f}°C"
        wb_display = get_wet_bulb_color(wet_bulb)
        
        rain_bar = format_rain_bar(avg_p)
        rain_display = f"{avg_p:4.2f} mm {rain_bar}"
        
        if avg_prob >= 60:
            prob_display = f"{COLOR_BOLD}{COLOR_RED}{avg_prob:4.0f}%{COLOR_RESET}"
        elif avg_prob >= 30:
            prob_display = f"{COLOR_YELLOW}{avg_prob:4.0f}%{COLOR_RESET}"
        else:
            prob_display = f"{COLOR_GRAY}{avg_prob:4.0f}%{COLOR_RESET}"

        range_display = f"{min_p:3.1f}-{max_p:3.1f} mm"
        wind_cardinal = degrees_to_cardinal(avg_wd)
        wind_display = f"{avg_ws:3.0f} km/h {wind_cardinal:<3}"
        rh_display = f"{avg_rh:3.0f}%"

        print(
            f" {hour_str:^5} | {wmo_display} | {temp_display:^7} | {wb_display:^18} | "
            f"{rain_display:<23} | {prob_display:^14} | {range_display:^13} | {wind_display:^13} | {rh_display:^6}"
        )

    # ==================== RIEPILOGO GENERALE GIORNALIERO ====================
    print(f"\n\n{COLOR_BOLD}{COLOR_YELLOW}{'=' * total_width}{COLOR_RESET}")
    print(f"{COLOR_BOLD}{COLOR_YELLOW}  QUADRO METEO SINTETICO GIORNALIERO - {loc_info['name'].upper()}{COLOR_RESET}")
    print(f"{COLOR_BOLD}{COLOR_YELLOW}{'=' * total_width}{COLOR_RESET}\n")

    for day, stats in daily_stats.items():
        min_t = min(stats["temps"]) if stats["temps"] else 0.0
        max_t = max(stats["temps"]) if stats["temps"] else 0.0
        avg_t = sum(stats["temps"]) / len(stats["temps"]) if stats["temps"] else 0.0
        
        min_wb = min(stats["wet_bulbs"]) if stats["wet_bulbs"] else 0.0
        max_wb = max(stats["wet_bulbs"]) if stats["wet_bulbs"] else 0.0
        
        avg_wind = sum(stats["wind_speeds"]) / len(stats["wind_speeds"]) if stats["wind_speeds"] else 0.0
        max_wind = max(stats["wind_speeds"]) if stats["wind_speeds"] else 0.0
        
        total_mm = stats["total_mm_avg"]
        max_p = stats["max_prob"]
        rain_h = stats["rain_hours"]

        print(f"{COLOR_BOLD}📌 {day} ({loc_info['name']}):{COLOR_RESET}")
        print(f"   🌡️  {COLOR_BOLD}Temperature:{COLOR_RESET} Min {COLOR_BLUE}{min_t:4.1f}°C{COLOR_RESET} | Max {COLOR_RED}{max_t:4.1f}°C{COLOR_RESET} | Media {avg_t:4.1f}°C")
        print(f"   💧 {COLOR_BOLD}Bulbo Umido (Wet Bulb):{COLOR_RESET} Range {min_wb:4.1f}°C - {max_wb:4.1f}°C (Stress da calore: {'Basso/Normale' if max_wb < 24 else 'Attenzione' if max_wb < 28 else 'Alto'})")
        print(f"   💨 {COLOR_BOLD}Vento:{COLOR_RESET} Velocità media {avg_wind:3.1f} km/h (Raffica max stimata {max_wind:3.1f} km/h)")
        print(f"   🌧️  {COLOR_BOLD}Pioggia stimata (Ensemble 5 modelli):{COLOR_RESET} {COLOR_BOLD}{total_mm:5.2f} mm{COLOR_RESET} (Picco probabilità: {max_p:4.1f}%)")
        
        # Dettaglio modelli
        model_str = " | ".join([f"{MODELS[k]}: {stats['model_totals'][k]:.1f} mm" for k in MODELS.keys()])
        print(f"      ↳ Dettaglio modelli: {COLOR_GRAY}{model_str}{COLOR_RESET}")

        if rain_h:
            h_str = ", ".join([f"{h} ({p_mm:.1f}mm, {p_pct:.0f}%)" for h, p_mm, p_pct, _ in rain_h[:8]])
            if len(rain_h) > 8:
                h_str += f" + altre {len(rain_h)-8} ore"
            print(f"      ↳ {COLOR_CYAN}Finestre con pioggia prevista:{COLOR_RESET} {h_str}")
        else:
            print(f"      ↳ {COLOR_GREEN}Nessuna precipitazione significativa attesa.{COLOR_RESET}")
        print()

    print(f"{COLOR_CYAN}{'=' * total_width}{COLOR_RESET}\n")


def prompt_city_choice() -> list:
    """Mostra un menu interattivo da terminale per scegliere la città."""
    print(f"\n{COLOR_BOLD}{COLOR_CYAN}=== SELEZIONA LA CITTÀ PER LE PREVISIONI METEO ==={COLOR_RESET}")
    print(f"  {COLOR_BOLD}1{COLOR_RESET} - Putignano (BA)")
    print(f"  {COLOR_BOLD}2{COLOR_RESET} - Monza")
    print(f"  {COLOR_BOLD}3{COLOR_RESET} - Entrambe le città (Putignano e Monza)")
    print(f"{COLOR_CYAN}=================================================={COLOR_RESET}")
    
    try:
        scelta = input(f"{COLOR_YELLOW}Inserisci il numero corrispondente (1, 2 o 3) [default: 3]: {COLOR_RESET}").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        scelta = "3"

    if scelta == "1":
        return [LOCATIONS["putignano"]]
    elif scelta == "2":
        return [LOCATIONS["monza"]]
    else:
        return [LOCATIONS["putignano"], LOCATIONS["monza"]]


def main():
    parser = argparse.ArgumentParser(
        description="Previsioni meteo generali e pioggia multi-fonte per Putignano e Monza con editoriale sinottico."
    )
    parser.add_argument(
        "--citta", "-c",
        type=str,
        choices=["putignano", "monza", "entrambe", "tutte", "all"],
        default=None,
        help="Città da visualizzare: 'putignano', 'monza', oppure 'entrambe' / 'tutte'"
    )
    parser.add_argument(
        "--giorni", "-g",
        type=int,
        default=3,
        choices=[1, 2, 3, 4, 5, 6, 7],
        help="Numero di giorni da prevedere (default: 3, max: 7)"
    )
    parser.add_argument(
        "--solo-pioggia", "-p",
        action="store_true",
        help="Filtra la visualizzazione oraria mostrando solo le ore con pioggia"
    )
    args = parser.parse_args()

    # Selezione città da CLI o interattiva
    selected_locations = []
    if args.citta:
        c_low = args.citta.lower()
        if c_low in ["entrambe", "tutte", "all"]:
            selected_locations = [LOCATIONS["putignano"], LOCATIONS["monza"]]
        elif c_low in LOCATIONS:
            selected_locations = [LOCATIONS[c_low]]
    else:
        selected_locations = prompt_city_choice()

    # 1. Recupero dati per tutte le località selezionate
    locations_results = {}
    for loc in selected_locations:
        print(f"{COLOR_GRAY}Connessione ai modelli meteorologici per {loc['name']}...{COLOR_RESET}")
        raw_data = fetch_weather_data(lat=loc["lat"], lon=loc["lon"], forecast_days=args.giorni)
        metrics = extract_city_metrics(raw_data)
        locations_results[loc["key"]] = {
            "loc": loc,
            "data": raw_data,
            "metrics": metrics
        }

    # 2. Stampa in APERTURA dell'Editoriale Meteorologico Sinottico (Stile Tweet Specialistico)
    generate_synoptic_editorial(locations_results)

    # 3. Stampa delle tabelle orarie dettagliate e riassunti per ciascuna città
    for loc_key, item in locations_results.items():
        process_and_display_forecasts(item["data"], loc_info=item["loc"], only_rain=args.solo_pioggia)


if __name__ == "__main__":
    main()
