#!/usr/bin/env python3
"""
Meteo Multi-Modello (Ensemble 5 Modelli) - Standalone Telegram Bot (Zero External Dependencies)
Bot Telegram completo per previsioni meteo, geocoding globale, coordinate GPS e monitor allerta pioggia multi-punto.
Utilizza esclusivamente la libreria standard Python (urllib, json, threading, http.server)
ed è ottimizzato per l'esecuzione locale e il deploy gratuito 24/7 su Cloud (Render, Railway, Koyeb).
"""

import sys
import os
import re
import math
import json
import time
import io
import argparse
import threading
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional, Tuple, Union
from http.server import HTTPServer, BaseHTTPRequestHandler

# Supporto rendering grafico con Pillow
try:
    from PIL import Image, ImageDraw, ImageFont, ImageEnhance
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# Assicura corretta gestione output UTF-8 su console Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ==============================================================================
# CONFIGURAZIONE E COSTANTI
# ==============================================================================
TELEGRAM_API_BASE = "https://api.telegram.org/bot"
CACHE_TTL_SECONDS = 300  # 5 minuti di cache per previsioni generali
HTTP_TIMEOUT = 25
MAX_RETRIES = 3
BASE_RETRY_DELAY = 1.0

# Località geografiche predefinite
DEFAULT_LOCATIONS = {
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
        "lat": 45.566708,
        "lon": 9.239812,
        "region": "Nord / Brianza - Pianura Padana",
        "desc": "Coordinate: 45.5667°N, 9.2398°E (Monza, Lombardia)"
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

# Livelli di degradazione adattiva per superare i rate-limit 429 di Open-Meteo
MODEL_TIERS = [
    ["ecmwf_ifs025", "dwd_icon_eu", "meteofrance_seamless", "gfs_global", "jma_seamless"],  # 5 modelli completi
    ["ecmwf_ifs025", "dwd_icon_eu", "meteofrance_seamless", "gfs_global"],                 # 4 modelli
    ["ecmwf_ifs025", "dwd_icon_eu", "gfs_global"],                                        # 3 modelli
    ["ecmwf_ifs025", "dwd_icon_eu"],                                                       # 2 modelli
    ["ecmwf_ifs025"],                                                                      # 1 modello (ECMWF)
    []                                                                                     # Fallback Best Match standard
]

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

# ==============================================================================
# CACHE MANAGER THREAD-SAFE (CON SUPPORTO LAST-KNOWN-GOOD FALLBACK)
# ==============================================================================
class CacheManager:
    def __init__(self, ttl_seconds: int = CACHE_TTL_SECONDS):
        self.ttl = ttl_seconds
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._last_known_good: Dict[str, Any] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            entry = self._cache.get(key)
            if not entry:
                return None
            if time.time() - entry["timestamp"] > self.ttl:
                del self._cache[key]
                return None
            return entry["data"]

    def set(self, key: str, data: Any) -> None:
        with self._lock:
            self._cache[key] = {
                "timestamp": time.time(),
                "data": data
            }
            self._last_known_good[key] = data

    def get_last_known_good(self, key: str) -> Optional[Any]:
        with self._lock:
            return self._last_known_good.get(key)

    def clear(self, key: Optional[str] = None) -> None:
        with self._lock:
            if key:
                self._cache.pop(key, None)
            else:
                self._cache.clear()

cache_store = CacheManager()

# ==============================================================================
# GEOCODING E PARSING COORDINATE (100% GRATUITO)
# ==============================================================================
def geocode_city(query_name: str) -> Optional[Dict[str, Any]]:
    """Interroga l'API Open-Meteo Geocoding per trovare le coordinate di una città."""
    clean_q = query_name.strip()
    if not clean_q:
        return None

    # Controllo cache
    cache_key = f"geo_{clean_q.lower()}"
    cached = cache_store.get(cache_key)
    if cached:
        return cached

    url = f"https://geocoding-api.open-meteo.com/v1/search?name={urllib.parse.quote(clean_q)}&count=1&language=it&format=json"
    req = urllib.request.Request(url, headers={"User-Agent": "Meteo-Telegram-Bot/3.0"})
    
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                results = data.get("results", [])
                if results:
                    top = results[0]
                    name = top.get("name", clean_q.capitalize())
                    country = top.get("country", "")
                    admin1 = top.get("admin1", "")
                    region_str = f"{admin1} ({country})" if admin1 and country else country or "Italia"
                    
                    loc_dict = {
                        "key": f"geo_{top.get('id', int(top.get('latitude', 0)*100))}",
                        "name": f"{name} ({top.get('country_code', 'IT')})",
                        "lat": float(top.get("latitude")),
                        "lon": float(top.get("longitude")),
                        "region": region_str,
                        "desc": f"Coordinate: {top.get('latitude'):.4f}°N, {top.get('longitude'):.4f}°E ({region_str})"
                    }
                    cache_store.set(cache_key, loc_dict)
                    return loc_dict
    except Exception as e:
        print(f"[!] Errore Geocoding per '{clean_q}': {e}", file=sys.stderr)
    return None


def parse_coordinates_text(text: str) -> Optional[Dict[str, Any]]:
    """Estrae coordinate geografiche (latitudine, longitudine) da una stringa testuale."""
    # Pattern: 40.8505, 17.1235 oppure 40.8505 17.1235
    match = re.search(r'([-+]?\d{1,2}(?:\.\d+)?)[,\s]+([-+]?\d{1,3}(?:\.\d+)?)', text.strip())
    if match:
        try:
            lat = float(match.group(1))
            lon = float(match.group(2))
            if -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0:
                return {
                    "key": f"coord_{lat:.4f}_{lon:.4f}",
                    "name": f"Coord ({lat:.3f}°N, {lon:.3f}°E)",
                    "lat": lat,
                    "lon": lon,
                    "region": "Punto GPS Personalizzato",
                    "desc": f"Coordinate GPS: {lat:.4f}°N, {lon:.4f}°E"
                }
        except Exception:
            pass
    return None


# ==============================================================================
# CALCOLI METEOROLOGICI ED ENSEMBLE
# ==============================================================================
def calculate_wet_bulb(temp_c: float, rh_pct: float) -> float:
    """
    Calcola la Temperatura di Bulbo Umido (Wet Bulb Temperature Tw in °C).
    Formula empirica di Roland Stull (2011).
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


def safe_float(val: Any, default: float = 0.0) -> float:
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def fetch_weather_data(lat: float, lon: float, forecast_days: int = 3) -> dict:
    """
    Interroga l'API Open-Meteo con degradazione adattiva a cascata su errore 429:
    5 modelli -> 4 modelli -> 3 modelli -> 2 modelli -> 1 modello -> Best Match.
    """
    last_error = None

    for tier_idx, models_subset in enumerate(MODEL_TIERS):
        if models_subset:
            models_query = f"&models={','.join(models_subset)}"
            tier_desc = f"{len(models_subset)} modelli ({', '.join([MODELS.get(m, m) for m in models_subset])})"
        else:
            models_query = ""
            tier_desc = "Open-Meteo Best Match (modello singolo ottimizzato)"

        url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            f"&hourly=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m,wind_direction_10m,precipitation,precipitation_probability"
            f"{models_query}"
            f"&forecast_days={forecast_days}"
            f"&timezone=auto"
        )

        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Meteo-Telegram-Bot/3.0 (Ensemble-Weather-Bot)"}
        )

        try:
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
                if resp.status == 200:
                    raw_json = json.loads(resp.read().decode("utf-8"))
                    raw_json["_tier_models"] = models_subset
                    return raw_json
        except urllib.error.HTTPError as http_err:
            last_error = http_err
            if http_err.code == 429:
                print(f"[!] Rate limit HTTP 429 rilevato su Open-Meteo per {lat},{lon}. Degradazione al livello successivo...", file=sys.stderr)
                time.sleep(0.3)
                continue  # Passa immediatamente al tier successivo con meno modelli
            elif tier_idx < len(MODEL_TIERS) - 1:
                time.sleep(0.5)
                continue
        except Exception as err:
            last_error = err
            if tier_idx < len(MODEL_TIERS) - 1:
                time.sleep(0.5)
                continue

    raise RuntimeError(f"Errore connessione Open-Meteo dopo degradazione completa: {last_error}")


def extract_city_metrics(data: dict) -> dict:
    """Estrae metriche aggregate e sintetiche supportando sia multi-modello che singolo best-match."""
    hourly = data.get("hourly", {})
    times = hourly.get("time", [])
    if not times:
        return {}

    active_keys = [m for m in MODELS.keys() if f"temperature_2m_{m}" in hourly]
    is_single_best_match = len(active_keys) == 0 and "temperature_2m" in hourly

    all_temps = []
    all_precips = []
    all_probs = []
    all_wbs = []
    days_data = {}

    for i, t_str in enumerate(times):
        dt = datetime.fromisoformat(t_str)
        day_str = dt.strftime("%Y-%m-%d")

        if is_single_best_match:
            t_val = safe_float(hourly.get("temperature_2m", [0])[i])
            p_val = safe_float(hourly.get("precipitation", [0])[i])
            pr_val = safe_float(hourly.get("precipitation_probability", [0])[i])
            rh_val = safe_float(hourly.get("relative_humidity_2m", [50])[i], 50.0)
            avg_t, avg_p, avg_pr, avg_rh = t_val, p_val, pr_val, rh_val
        else:
            t_vals = [safe_float(hourly.get(f"temperature_2m_{m}", [None])[i]) for m in active_keys if hourly.get(f"temperature_2m_{m}") is not None]
            p_vals = [safe_float(hourly.get(f"precipitation_{m}", [None])[i]) for m in active_keys if hourly.get(f"precipitation_{m}") is not None]
            pr_vals = [safe_float(hourly.get(f"precipitation_probability_{m}", [None])[i]) for m in active_keys if hourly.get(f"precipitation_probability_{m}") is not None]
            rh_vals = [safe_float(hourly.get(f"relative_humidity_2m_{m}", [None])[i], 50.0) for m in active_keys if hourly.get(f"relative_humidity_2m_{m}") is not None]

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
        "max_temp": max(all_temps) if all_temps else 0.0,
        "min_temp": min(all_temps) if all_temps else 0.0,
        "avg_temp": sum(all_temps) / len(all_temps) if all_temps else 0.0,
        "max_wb": max(all_wbs) if all_wbs else 0.0,
        "total_rain": sum(all_precips) if all_precips else 0.0,
        "max_rain_prob": max(all_probs) if all_probs else 0.0,
        "days": days_data
    }


def resolve_location(target: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Risolve un target in un dizionario di località valido (stringa chiave predefinita o dict)."""
    if isinstance(target, dict) and "lat" in target and "lon" in target:
        return target
    if isinstance(target, str):
        low = target.lower().strip()
        if low in DEFAULT_LOCATIONS:
            return DEFAULT_LOCATIONS[low]
        # Prova parsing coordinate
        parsed_coord = parse_coordinates_text(target)
        if parsed_coord:
            return parsed_coord
        # Prova geocoding
        geocoded = geocode_city(target)
        if geocoded:
            return geocoded
    return DEFAULT_LOCATIONS["putignano"]


def parse_location_forecast(target: Union[str, Dict[str, Any]], force_refresh: bool = False, days: int = 3) -> Dict[str, Any]:
    """Ottiene i dati meteo per una località con supporto degradazione modelli e fallback resiliente su cache."""
    loc_info = resolve_location(target)

    cache_key = f"meteo_{loc_info['lat']:.4f}_{loc_info['lon']:.4f}_{days}"
    if not force_refresh:
        cached = cache_store.get(cache_key)
        if cached:
            return cached

    try:
        raw_data = fetch_weather_data(lat=loc_info["lat"], lon=loc_info["lon"], forecast_days=days)
    except Exception as e:
        # Se tutte le chiamate API falliscono (es. 429 persistente), tenta fallback su cache last-known-good
        fallback_data = cache_store.get_last_known_good(cache_key)
        if fallback_data:
            print(f"[!] Chiamata live fallita ({e}). Fallback su ultima cache valida.", file=sys.stderr)
            fallback_data["is_stale_fallback"] = True
            return fallback_data
        raise e

    metrics = extract_city_metrics(raw_data)

    # Calcolo esatto dell'orario locale italiano (indipendentemente dal server cloud che gira in UTC)
    offset_seconds = raw_data.get("utc_offset_seconds", 7200)
    utc_now = datetime.now(timezone.utc)
    local_now = (utc_now + timedelta(seconds=offset_seconds)).replace(tzinfo=None)

    hourly = raw_data.get("hourly", {})
    times = hourly.get("time", [])

    # Rileva quali modelli sono presenti nei dati
    active_keys = [m for m in MODELS.keys() if f"temperature_2m_{m}" in hourly]
    is_single_best_match = len(active_keys) == 0 and "temperature_2m" in hourly

    daily_stats: Dict[str, Any] = {}
    hours_list: List[Dict[str, Any]] = []

    for i, t_str in enumerate(times):
        dt = datetime.fromisoformat(t_str)
        day_en = dt.strftime("%A")
        day_ita = GIORNI_ITA.get(day_en, day_en)
        day_str = f"{day_ita} {dt.strftime('%d/%m')}"
        hour_str = dt.strftime("%H:%M")

        if day_str not in daily_stats:
            daily_stats[day_str] = {
                "day_label": day_str,
                "temps": [],
                "wet_bulbs": [],
                "wind_speeds": [],
                "wind_dirs": [],
                "total_mm_avg": 0.0,
                "max_prob": 0.0,
                "rain_slots": [],
                "model_totals": {k: 0.0 for k in (active_keys if active_keys else ["best_match"])}
            }

        precip_vals = []
        prob_vals = []
        temp_vals = []
        rh_vals = []
        wind_spd_vals = []
        wind_dir_vals = []
        wmo_vals = []
        model_temps = {}

        if is_single_best_match:
            p = safe_float(hourly.get("precipitation", [0])[i])
            pr = safe_float(hourly.get("precipitation_probability", [0])[i])
            t = safe_float(hourly.get("temperature_2m", [0])[i])
            rh = safe_float(hourly.get("relative_humidity_2m", [50])[i], 50.0)
            ws = safe_float(hourly.get("wind_speed_10m", [0])[i])
            wd = safe_float(hourly.get("wind_direction_10m", [0])[i])
            wmo = int(hourly.get("weather_code", [0])[i] or 0)

            precip_vals.append(p)
            prob_vals.append(pr)
            temp_vals.append(t)
            model_temps["best_match"] = t
            rh_vals.append(rh)
            wind_spd_vals.append(ws)
            wind_dir_vals.append(wd)
            wmo_vals.append(wmo)
            daily_stats[day_str]["model_totals"]["best_match"] += p
        else:
            for m_key in active_keys:
                p = hourly.get(f"precipitation_{m_key}", [0])[i]
                pr = hourly.get(f"precipitation_probability_{m_key}", [0])[i]
                t = hourly.get(f"temperature_2m_{m_key}", [0])[i]
                rh = hourly.get(f"relative_humidity_2m_{m_key}", [0])[i]
                ws = hourly.get(f"wind_speed_10m_{m_key}", [0])[i]
                wd = hourly.get(f"wind_direction_10m_{m_key}", [0])[i]
                wmo = hourly.get(f"weather_code_{m_key}", [0])[i]

                if p is not None: precip_vals.append(float(p))
                if pr is not None: prob_vals.append(float(pr))
                if t is not None:
                    temp_vals.append(float(t))
                    model_temps[m_key] = float(t)
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
        wet_bulb = calculate_wet_bulb(avg_temp, avg_rh)

        daily_stats[day_str]["temps"].append(avg_temp)
        daily_stats[day_str]["wet_bulbs"].append(wet_bulb)
        daily_stats[day_str]["wind_speeds"].append(avg_ws)
        daily_stats[day_str]["wind_dirs"].append(avg_wd)
        daily_stats[day_str]["total_mm_avg"] += avg_p
        
        if avg_prob > daily_stats[day_str]["max_prob"]:
            daily_stats[day_str]["max_prob"] = avg_prob
        
        if avg_p > 0.05 or avg_prob >= 25:
            daily_stats[day_str]["rain_slots"].append({
                "hour": hour_str,
                "mm": avg_p,
                "prob": avg_prob,
                "label": wmo_label,
                "icon": wmo_icon
            })

        hours_list.append({
            "iso_time": t_str,
            "dt": dt,
            "day": day_str,
            "hour": hour_str,
            "temp": avg_temp,
            "model_temps": model_temps,
            "wet_bulb": wet_bulb,
            "humidity": avg_rh,
            "rain_mm": avg_p,
            "rain_prob": avg_prob,
            "wind_spd": avg_ws,
            "wind_dir": degrees_to_cardinal(avg_wd),
            "wmo_icon": wmo_icon,
            "wmo_label": wmo_label
        })

    result_data = {
        "loc": loc_info,
        "metrics": metrics,
        "daily": daily_stats,
        "hours": hours_list,
        "active_models": active_keys if active_keys else ["best_match"],
        "model_count": len(active_keys) if active_keys else 1,
        "is_stale_fallback": False,
        "local_now": local_now,
        "updated_at": local_now.strftime("%d/%m/%Y alle %H:%M:%S")
    }

    cache_store.set(cache_key, result_data)
    return result_data


# ==============================================================================
# FORMATTAZIONE MESSAGGI TELEGRAM
# ==============================================================================
def format_current_weather_message(data: Dict[str, Any]) -> str:
    """Formatta la scheda per le condizioni meteorologiche in tempo reale (Adesso)."""
    loc = data["loc"]
    hours = data.get("hours", [])
    local_now = data.get("local_now", datetime.now())
    updated_at = data.get("updated_at", "")

    if not hours:
        return f"⚠️ Dati meteo non disponibili per {loc['name']}."

    closest_slot = min(hours, key=lambda h: abs((h["dt"] - local_now).total_seconds()))
    
    cur_t = closest_slot["temp"]
    cur_wb = closest_slot["wet_bulb"]
    cur_rh = closest_slot["humidity"]
    cur_ws = closest_slot["wind_spd"]
    cur_wd = closest_slot["wind_dir"]
    cur_icon = closest_slot["wmo_icon"]
    cur_label = closest_slot["wmo_label"]
    cur_rain = closest_slot["rain_mm"]
    cur_prob = closest_slot["rain_prob"]

    # Stress termico
    if cur_wb < 18.0:
        stress_badge = "🟢 Basso / Confortevole"
    elif cur_wb < 24.0:
        stress_badge = "🟢 Normale"
    elif cur_wb < 28.0:
        stress_badge = "🟡 Attenzione / Afa percepita"
    elif cur_wb < 30.0:
        stress_badge = "🟠 Stress termico significativo"
    else:
        stress_badge = "🔴 PERICOLO / Afa estrema"

    # Dettaglio modelli
    m_temps = closest_slot.get("model_temps", {})
    if "best_match" in m_temps:
        m_temp_str = f"Open-Meteo Best Match: <code>{m_temps['best_match']:.1f}°C</code>"
    else:
        m_temp_str = " • ".join([f"{MODELS[k]}: <code>{m_temps[k]:.1f}°C</code>" for k in MODELS.keys() if k in m_temps])

    # Trend prossime 3 ore
    cur_idx = hours.index(closest_slot)
    next_slots = hours[cur_idx+1 : cur_idx+4]
    trend_lines = []
    for s in next_slots:
        trend_lines.append(f"• <b>{s['hour']}</b>: {s['wmo_icon']} <code>{s['temp']:.1f}°C</code> | Tw <code>{s['wet_bulb']:.1f}°C</code> | 🌧️ {s['rain_mm']:.1f}mm ({s['rain_prob']:.0f}%)")
    trend_text = "\n".join(trend_lines) if trend_lines else "Nessuna proiezione oraria successiva."

    model_count_str = f"Media {len(data.get('active_models', []))} Modelli" if "best_match" not in data.get("active_models", []) else "Modello Singolo Ottimizzato"

    out = [
        "🌡️ <b>METEO IN TEMPO REALE</b>",
        f"🏙️ <b>{loc['name'].upper()}</b>",
        f"📍 <i>{loc.get('desc', loc.get('region', ''))}</i>",
        f"⏱️ <i>Fascia oraria attiva: {closest_slot['day']} ore {closest_slot['hour']}</i>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"{cur_icon} <b>Condizione:</b> {cur_label}",
        f"🌡️ <b>Temperatura Live:</b> <code>{cur_t:.1f}°C</code> ({model_count_str})",
        f"💧 <b>Bulbo Umido (Wet Bulb):</b> <code>{cur_wb:.1f}°C</code>\n   └ Indice stress: <i>{stress_badge}</i>",
        f"💦 <b>Umidità Relativa:</b> <code>{cur_rh:.0f}%</code>",
        f"💨 <b>Vento:</b> <code>{cur_ws:.1f} km/h</code> da <code>{cur_wd}</code>",
        f"🌧️ <b>Precipitazione oraria:</b> <code>{cur_rain:.2f} mm</code> (Prob. <code>{cur_prob:.0f}%</code>)\n",
        "🔬 <b>CONFRONTO MODELLI ATTIVI:</b>",
        f"{m_temp_str}\n",
        "🕒 <b>TENDENZA PROSSIME 3 ORE:</b>",
        trend_text,
        "━━━━━━━━━━━━━━━━━━━━"
    ]

    if data.get("is_stale_fallback"):
        out.append(f"⚠️ <i>Dati in cache ({updated_at}) • Modalità Risparmio API attiva</i>")
    else:
        out.append(f"🕒 <i>Rilevamento delle {updated_at} • Ensemble Open-Meteo</i>")

    return "\n".join(out)


def format_city_weather_message(data: Dict[str, Any], only_rain: bool = False) -> str:
    loc = data["loc"]
    daily = data["daily"]
    updated_at = data.get("updated_at", "")
    active_m = data.get("active_models", list(MODELS.keys()))

    if "best_match" in active_m:
        m_head_str = "Modello Singolo Ottimizzato (Best Match)"
    else:
        m_head_str = f"{len(active_m)} Modelli: " + ", ".join([MODELS.get(k, k) for k in active_m])

    header = [
        f"📍 <b>PREVISIONI METEO ENSEMBLE (3 GIORNI)</b>",
        f"🏙️ <b>{loc['name'].upper()}</b>",
        f"🧭 <i>{loc.get('desc', loc.get('region', ''))}</i>",
        f"🔬 <i>{m_head_str}</i>",
        "━━━━━━━━━━━━━━━━━━━━"
    ]

    body = []
    for day_str, stats in daily.items():
        min_t = min(stats["temps"]) if stats["temps"] else 0.0
        max_t = max(stats["temps"]) if stats["temps"] else 0.0
        avg_t = sum(stats["temps"]) / len(stats["temps"]) if stats["temps"] else 0.0
        max_wb = max(stats["wet_bulbs"]) if stats["wet_bulbs"] else 0.0
        total_mm = stats["total_mm_avg"]
        max_prob = stats["max_prob"]
        rain_slots = stats["rain_slots"]

        # Indice stress termico
        stress_label = "🟢 Normale" if max_wb < 24 else "🟡 Attenzione" if max_wb < 28 else "🔴 Stress Elevato"

        day_block = [
            f"📅 <b>{day_str.upper()}</b>",
            f"🌡️ <b>Temp:</b> Min <code>{min_t:.1f}°C</code> | Max <code>{max_t:.1f}°C</code> (Med <code>{avg_t:.1f}°C</code>)",
            f"💧 <b>Bulbo Umido (Tw):</b> Max <code>{max_wb:.1f}°C</code> ({stress_label})",
            f"🌧️ <b>Pioggia stimata:</b> <code>{total_mm:.2f} mm</code> (Picco prob: <code>{max_prob:.0f}%</code>)"
        ]

        # Dettaglio modelli
        if "best_match" in stats["model_totals"]:
            model_str = f"Best Match: <code>{stats['model_totals']['best_match']:.1f}mm</code>"
        else:
            model_str = " • ".join([f"{MODELS[k]}: <code>{stats['model_totals'][k]:.1f}mm</code>" for k in active_m if k in stats["model_totals"]])
        day_block.append(f"   ↳ <i>Modelli:</i> {model_str}")

        # Finestre di pioggia
        if rain_slots:
            r_lines = []
            for slot in rain_slots[:6]:
                r_lines.append(f"<code>{slot['hour']}</code> {slot['icon']} {slot['mm']:.1f}mm ({slot['prob']:.0f}%)")
            slot_str = " | ".join(r_lines)
            if len(rain_slots) > 6:
                slot_str += f" (+ altre {len(rain_slots)-6}h)"
            day_block.append(f"   ↳ 🌧️ <b>Ore pioggia:</b> {slot_str}")
        else:
            if not only_rain:
                day_block.append("   ↳ ☀️ <i>Nessuna pioggia significativa prevista.</i>")

        body.append("\n".join(day_block))

    footer = [
        "━━━━━━━━━━━━━━━━━━━━",
        f"⚠️ <i>Dati in cache ({updated_at}) • Risparmio API attivo</i>" if data.get("is_stale_fallback") else f"🕒 <i>Aggiornato alle {updated_at} • Dati Open-Meteo</i>"
    ]

    return "\n\n".join(["\n".join(header), "\n\n".join(body), "\n".join(footer)])


def format_single_city_synoptic_message(data: Dict[str, Any], city_label: str) -> str:
    """Genera l'editoriale sinottico dettagliato e specifico per qualsiasi città o coordinata."""
    loc = data["loc"]
    m = data.get("metrics", {})
    updated_at = data.get("updated_at", "")

    max_t = m.get("max_temp", 30.0)
    min_t = m.get("min_temp", 18.0)
    avg_t = m.get("avg_temp", 24.0)
    tot_r = m.get("total_rain", 0.0)
    max_pr = m.get("max_rain_prob", 0.0)
    max_wb = m.get("max_wb", 22.0)

    is_rainy = tot_r > 3.0 or max_pr >= 40
    is_hot = max_t >= 32.0 or max_wb >= 25.0

    if "putignano" in loc["key"].lower():
        title_str = "🔥 <b>QUADRO SINOTTICO: PUTIGNANO & MURGE BARESI</b>"
        sub_title = "<b>Pulsazione calda anticiclonica, compressione dell'aria e stabilità sul versante adriatico.</b>"
        extra_note = "L'evoluzione sul settore centrale delle Murge è dominata dalla risalita di una matrice subtropicale continentale."
    elif "monza" in loc["key"].lower():
        title_str = "⛈️ <b>QUADRO SINOTTICO: MONZA & ALTA PIANURA PADANA</b>"
        sub_title = "<b>Fase prefrontale caldo-umida, elevata afa e cedimento instabile con rischio temporali.</b>"
        extra_note = "La Brianza si colloca lungo il bordo settentrionale di convergenza tra il richiamo caldo e le infiltrazioni atlantiche."
    else:
        title_str = f"📡 <b>QUADRO SINOTTICO DEDICATO: {loc['name'].upper()}</b>"
        if is_rainy:
            sub_title = "<b>Assetto instabile con passaggi perturbati o contrasti convettivi significativi.</b>"
        elif is_hot:
            sub_title = "<b>Regime anticiclonico caldo con marcata compressione termica al suolo.</b>"
        else:
            sub_title = "<b>Condizioni di generale equilibrio barico con circolazione standard.</b>"
        extra_note = f"Analisi specifica calcolata per le coordinate {loc['lat']:.4f}°N, {loc['lon']:.4f}°E ({loc.get('region', '')})."

    synopsis_body = (
        f"{extra_note}\n\n"
        "📌 <b>Dinamica Termo-Igorometrica & Modelli:</b>\n"
        f"• <b>Comportamento Termico:</b> Picco massimo atteso a <code>{max_t:.1f}°C</code> (minima notturna <code>{min_t:.1f}°C</code>, media <code>{avg_t:.1f}°C</code>).\n"
        f"• <b>Bulbo Umido (Wet Bulb Tw):</b> Valore max <code>{max_wb:.1f}°C</code> ({'Aria asciutta / Comfort' if max_wb < 24 else 'Afa percepita' if max_wb < 28 else 'Stress termico elevato'}).\n"
        f"• <b>Assetto Precipitativo:</b> Cumulato totale sui 3 giorni stimato in <code>{tot_r:.1f} mm</code> (picco di probabilità al <code>{max_pr:.0f}%</code>)."
    )

    out = [
        title_str,
        f"📍 <i>Analisi multi-modello specifica per {loc['name']}</i>",
        "━━━━━━━━━━━━━━━━━━━━",
        sub_title,
        "\n🧭 <b>ANALISI METEOROLOGICA SPECIALISTICA:</b>",
        synopsis_body,
        "\n━━━━━━━━━━━━━━━━━━━━",
        f"🕒 <i>Editoriale elaborato alle {updated_at} • Meteo Ensemble Bot</i>"
    ]
    return "\n".join(out)


# ==============================================================================
# GENERAZIONE MAPPA METEO STATICA GRAFICA (PILLOW & OPENSTREETMAP TILES)
# ==============================================================================
OSM_TILE_CACHE: Dict[str, bytes] = {}
OSM_CACHE_LOCK = threading.Lock()


def get_map_font(size: int = 14, bold: bool = False) -> Any:
    """Carica un font TrueType di sistema o esegue fallback sul font bitmap di default."""
    if not HAS_PIL:
        return None
    font_candidates = [
        "C:\\Windows\\Fonts\\arialbd.ttf" if bold else "C:\\Windows\\Fonts\\arial.ttf",
        "C:\\Windows\\Fonts\\segoeuib.ttf" if bold else "C:\\Windows\\Fonts\\segoeui.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
        "arial.ttf"
    ]
    for path in font_candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    try:
        return ImageFont.load_default(size=size)
    except Exception:
        return ImageFont.load_default()


def generate_static_weather_map(loc: Dict[str, Any], data: Dict[str, Any]) -> Optional[bytes]:
    """Genera un'immagine PNG (640x480) con mappa stradale/topografica e cartellini meteo ad alto contrasto."""
    if not HAS_PIL:
        return None

    lat = float(loc.get("lat", 40.8505))
    lon = float(loc.get("lon", 17.1235))
    name = loc.get("name", "Località")
    
    hours = data.get("hours", [])
    local_now = data.get("local_now", datetime.now())
    closest_slot = min(hours, key=lambda h: abs((h["dt"] - local_now).total_seconds())) if hours else {}
    
    temp = closest_slot.get("temp", 20.0)
    wmo_label = closest_slot.get("wmo_label", "Sereno")
    
    daily = data.get("daily", {})
    first_day = next(iter(daily.values())) if daily else {}
    rain_24h = first_day.get("total_mm_avg", 0.0)
    rain_prob = int(first_day.get("max_prob", 0))
    updated_at = data.get("updated_at", "")

    # Calcolo coordinate Slippy Map a Zoom 11 (~30 km di visuale territoriale)
    zoom = 11
    lat_rad = math.radians(lat)
    n = 1 << zoom
    center_xf = (lon + 180.0) / 360.0 * n
    center_yf = (1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n
    center_xi = int(center_xf)
    center_yi = int(center_yf)

    tile_grid = Image.new("RGB", (256 * 3, 256 * 3), color=(15, 23, 42))
    headers = {"User-Agent": "MeteoEnsembleBot/1.0 (https://github.com/meteo)"}
    
    osm_ok = False
    for dx in range(-1, 2):
        for dy in range(-1, 2):
            tx = center_xi + dx
            ty = center_yi + dy
            tile_key = f"{zoom}_{tx}_{ty}"
            tile_bytes = None
            
            with OSM_CACHE_LOCK:
                tile_bytes = OSM_TILE_CACHE.get(tile_key)
                
            if not tile_bytes:
                tile_url = f"https://tile.openstreetmap.org/{zoom}/{tx}/{ty}.png"
                try:
                    req = urllib.request.Request(tile_url, headers=headers)
                    with urllib.request.urlopen(req, timeout=3.5) as resp:
                        tile_bytes = resp.read()
                        with OSM_CACHE_LOCK:
                            if len(OSM_TILE_CACHE) > 100:
                                OSM_TILE_CACHE.clear()
                            OSM_TILE_CACHE[tile_key] = tile_bytes
                except Exception:
                    pass
                    
            if tile_bytes:
                try:
                    t_img = Image.open(io.BytesIO(tile_bytes)).convert("RGB")
                    tile_grid.paste(t_img, ((dx + 1) * 256, (dy + 1) * 256))
                    osm_ok = True
                except Exception:
                    pass

    width, height = 640, 480
    if osm_ok:
        px = int((center_xf - (center_xi - 1)) * 256)
        py = int((center_yf - (center_yi - 1)) * 256)
        
        left = max(0, min(768 - width, px - width // 2))
        top = max(0, min(768 - height, py - height // 2))
        cropped = tile_grid.crop((left, top, left + width, top + height))
        
        enhancer = ImageEnhance.Brightness(cropped)
        base_img = enhancer.enhance(0.70)
    else:
        # Fallback dark radar grid
        base_img = Image.new("RGB", (width, height), color=(15, 23, 42))
        d_fb = ImageDraw.Draw(base_img)
        for gx in range(0, width, 40):
            d_fb.line([(gx, 0), (gx, height)], fill=(30, 41, 59), width=1)
        for gy in range(0, height, 40):
            d_fb.line([(0, gy), (width, gy)], fill=(30, 41, 59), width=1)

    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    font_title = get_map_font(18, bold=True)
    font_sub = get_map_font(12, bold=False)
    font_badge = get_map_font(13, bold=True)
    font_temp = get_map_font(26, bold=True)
    font_val = get_map_font(14, bold=True)
    font_text = get_map_font(13, bold=False)
    font_tiny = get_map_font(11, bold=False)

    # 1. Location Pin centrale
    pin_x, pin_y = width // 2, height // 2
    draw.ellipse([pin_x - 32, pin_y - 32, pin_x + 32, pin_y + 32], fill=(56, 189, 248, 45), outline=(56, 189, 248, 200), width=2)
    draw.ellipse([pin_x - 14, pin_y - 14, pin_x + 14, pin_y + 14], fill=(239, 68, 68, 230), outline=(255, 255, 255, 255), width=2)
    draw.ellipse([pin_x - 4, pin_y - 4, pin_x + 4, pin_y + 4], fill=(255, 255, 255, 255))

    # 2. Header Top Bar
    draw.rounded_rectangle([18, 14, width - 18, 68], radius=12, fill=(15, 23, 42, 235), outline=(56, 189, 248, 180), width=2)
    draw.text((32, 22), f"MAPPA METEO: {name.upper()}", fill=(255, 255, 255), font=font_title)
    draw.text((32, 46), f"Coord: {lat:.4f}°N, {lon:.4f}°E  •  Raggio visuale: ~30 km", fill=(148, 163, 184), font=font_sub)

    # 3. Card Sinistra: Temperatura & Condizione Attuale
    draw.rounded_rectangle([18, height - 150, 310, height - 16], radius=14, fill=(15, 23, 42, 240), outline=(251, 146, 60, 220), width=2)
    draw.text((32, height - 140), "TEMPERATURA ATTUALE", fill=(251, 146, 60), font=font_badge)
    draw.text((32, height - 116), f"{temp:.1f} °C", fill=(255, 255, 255), font=font_temp)
    draw.text((32, height - 74), f"Condizione: {wmo_label}", fill=(226, 232, 240), font=font_text)
    draw.text((32, height - 50), f"Rilevamento: {updated_at}", fill=(148, 163, 184), font=font_tiny)

    # 4. Card Destra: Pioggia & Precipitazioni 24h
    draw.rounded_rectangle([330, height - 150, width - 18, height - 16], radius=14, fill=(15, 23, 42, 240), outline=(56, 189, 248, 220), width=2)
    draw.text((344, height - 140), "PRECIPITAZIONI 24H", fill=(56, 189, 248), font=font_badge)
    draw.text((344, height - 114), f"Probabilità: {rain_prob}%", fill=(255, 255, 255), font=font_val)
    draw.text((344, height - 88), f"Accumulo previsto: {rain_24h:.1f} mm", fill=(226, 232, 240), font=font_text)
    
    status_color = (74, 222, 128) if rain_prob < 30 else (250, 204, 21) if rain_prob < 60 else (248, 113, 113)
    status_text = "Rischio Basso" if rain_prob < 30 else "Rischio Moderato" if rain_prob < 60 else "Allerta Pioggia ⚠️"
    draw.text((344, height - 54), f"Stato: {status_text}", fill=status_color, font=font_badge)

    final_img = Image.alpha_composite(base_img.convert("RGBA"), overlay)
    
    out_buf = io.BytesIO()
    final_img.convert("RGB").save(out_buf, format="PNG", optimize=True)
    return out_buf.getvalue()


def get_inline_keyboard(loc_info: Dict[str, Any], current_tab: str = "forecast", only_rain: bool = False, alert_on: bool = False) -> Dict[str, Any]:
    """Genera la tastiera inline dinamica con selezione città, tab e controlli alert."""
    cur_key = loc_info.get("key", "putignano")

    put_label = "👉 📍 Putignano" if cur_key == "putignano" else "📍 Putignano"
    mon_label = "👉 📍 Monza" if cur_key == "monza" else "📍 Monza"

    now_label = "👉 🌡️ Adesso" if current_tab == "now" else "🌡️ Adesso"
    fore_label = "👉 📅 Previsioni 3gg" if current_tab == "forecast" else "📅 Previsioni 3gg"
    syn_label = "👉 📡 Sinottico" if current_tab == "synoptic" else "📡 Sinottico"
    map_label = "👉 🗺️ Mappa" if current_tab == "map" else "🗺️ Mappa"

    rain_label = "🌧️ Solo Pioggia (ATTIVO)" if only_rain else "🌧️ Solo Pioggia"
    alert_label = "🔔 Alert Pioggia: ON" if alert_on else "🔕 Alert Pioggia: OFF"

    # Riga 1: Predefinite o indicatore località attiva
    row1 = [
        {"text": put_label, "callback_data": f"loc_putignano_{current_tab}"},
        {"text": mon_label, "callback_data": f"loc_monza_{current_tab}"}
    ]

    # Se la località corrente è personalizzata (non Putignano e non Monza), mostra badge
    if cur_key not in ("putignano", "monza"):
        loc_short = loc_info.get("name", "Custom")[:16]
        row1.append({"text": f"👉 📍 {loc_short}", "callback_data": f"loc_custom_{current_tab}"})

    return {
        "inline_keyboard": [
            row1,
            [
                {"text": now_label, "callback_data": f"tab_{current_tab}_now"},
                {"text": fore_label, "callback_data": f"tab_{current_tab}_forecast"},
                {"text": syn_label, "callback_data": f"tab_{current_tab}_synoptic"}
            ],
            [
                {"text": map_label, "callback_data": f"show_map_{cur_key}"},
                {"text": rain_label, "callback_data": f"toggle_rain_{'off' if only_rain else 'on'}"},
                {"text": alert_label, "callback_data": f"toggle_alert_{'off' if alert_on else 'on'}"}
            ],
            [
                {"text": "🔍 Cerca Altra Città / GPS", "callback_data": "help_search"},
                {"text": "🔄 Aggiorna Live", "callback_data": f"refresh_{current_tab}"}
            ]
        ]
    }


# ==============================================================================
# TELEGRAM API CLIENT NATIVO (Zero-Deps)
# ==============================================================================
class TelegramBotClient:
    def __init__(self, token: str):
        self.token = token.strip()
        self.base_url = f"{TELEGRAM_API_BASE}{self.token}"

    def _call(self, method: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{self.base_url}/{method}"
        data = json.dumps(payload).encode("utf-8") if payload else None
        headers = {"Content-Type": "application/json"} if payload else {}
        req = urllib.request.Request(url, data=data, headers=headers)

        for attempt in range(MAX_RETRIES):
            try:
                with urllib.request.urlopen(req, timeout=35) as res:
                    raw = res.read().decode("utf-8")
                    parsed = json.loads(raw)
                    if not parsed.get("ok"):
                        raise RuntimeError(f"Telegram API error: {parsed.get('description')}")
                    return parsed
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    time.sleep(2.0)
                    continue
                raw_err = e.read().decode("utf-8", errors="ignore")
                raise RuntimeError(f"HTTP {e.code}: {raw_err}") from e
            except Exception as e:
                if attempt == MAX_RETRIES - 1:
                    raise RuntimeError(f"Errore di rete Telegram: {e}") from e
                time.sleep(1.0)
        return {"ok": False}

    def get_me(self) -> Dict[str, Any]:
        return self._call("getMe")

    def get_updates(self, offset: Optional[int] = None, timeout: int = 30) -> List[Dict[str, Any]]:
        payload: Dict[str, Any] = {"timeout": timeout, "allowed_updates": ["message", "callback_query"]}
        if offset is not None:
            payload["offset"] = offset
        res = self._call("getUpdates", payload)
        return res.get("result", [])

    def send_message(self, chat_id: Union[int, str], text: str, reply_markup: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        return self._call("sendMessage", payload)

    def edit_message_text(self, chat_id: Union[int, str], message_id: int, text: str, reply_markup: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        return self._call("editMessageText", payload)

    def answer_callback_query(self, callback_query_id: str, text: Optional[str] = None) -> None:
        payload: Dict[str, Any] = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
            payload["show_alert"] = False
        try:
            self._call("answerCallbackQuery", payload)
        except Exception:
            pass

    def send_photo(self, chat_id: Union[int, str], photo_bytes: bytes, caption: Optional[str] = None, reply_markup: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Invia un'immagine binaria PNG a Telegram usando multipart/form-data nativo."""
        boundary = "----WebKitFormBoundary" + str(int(time.time() * 1000))
        body = bytearray()
        
        # chat_id
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(f'Content-Disposition: form-data; name="chat_id"\r\n\r\n{chat_id}\r\n'.encode("utf-8"))
        
        # caption
        if caption:
            body.extend(f"--{boundary}\r\n".encode("utf-8"))
            body.extend(f'Content-Disposition: form-data; name="caption"\r\n\r\n{caption}\r\n'.encode("utf-8"))
            body.extend(f"--{boundary}\r\n".encode("utf-8"))
            body.extend(b'Content-Disposition: form-data; name="parse_mode"\r\n\r\nHTML\r\n')
            
        # reply_markup
        if reply_markup:
            body.extend(f"--{boundary}\r\n".encode("utf-8"))
            body.extend(f'Content-Disposition: form-data; name="reply_markup"\r\n\r\n{json.dumps(reply_markup)}\r\n'.encode("utf-8"))
            
        # photo file
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(b'Content-Disposition: form-data; name="photo"; filename="map.png"\r\n')
        body.extend(b'Content-Type: image/png\r\n\r\n')
        body.extend(photo_bytes)
        body.extend(b'\r\n')
        
        body.extend(f"--{boundary}--\r\n".encode("utf-8"))
        
        req = urllib.request.Request(
            f"{self.base_url}/sendPhoto",
            data=bytes(body),
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "User-Agent": "MeteoEnsembleBot/1.0"
            },
            method="POST"
        )
        for attempt in range(MAX_RETRIES):
            try:
                with urllib.request.urlopen(req, timeout=35) as res:
                    raw = res.read().decode("utf-8")
                    parsed = json.loads(raw)
                    if not parsed.get("ok"):
                        raise RuntimeError(f"Telegram API error: {parsed.get('description')}")
                    return parsed
            except Exception as e:
                if attempt == MAX_RETRIES - 1:
                    raise RuntimeError(f"Errore invio foto Telegram: {e}") from e
                time.sleep(1.0)
        return {"ok": False}

    def set_commands(self) -> None:
        commands = [
            {"command": "start", "description": "Apri il menu meteo principale"},
            {"command": "adesso", "description": "Temperatura e meteo in tempo reale"},
            {"command": "mappa", "description": "Mappa grafica PNG con dati meteo e pioggia"},
            {"command": "putignano", "description": "Previsioni 3 giorni per Putignano"},
            {"command": "monza", "description": "Previsioni 3 giorni per Monza"},
            {"command": "citta", "description": "Cerca qualsiasi città (es. /citta Roma)"},
            {"command": "coord", "description": "Previsioni per coordinate GPS (es. /coord 40.85 17.12)"},
            {"command": "sinottico", "description": "Quadro sinottico specialistico"},
            {"command": "alert_on", "description": "Attiva gli avvisi di pioggia imminente"},
            {"command": "alert_off", "description": "Disattiva gli avvisi di pioggia"},
            {"command": "alert_punto1", "description": "Imposta il Punto 1 di allerta (es. /alert_punto1 Putignano)"},
            {"command": "alert_punto2", "description": "Imposta il Punto 2 di allerta (es. /alert_punto2 Monza)"},
            {"command": "alert_status", "description": "Verifica lo stato dei 2 punti monitorati"},
            {"command": "pioggia", "description": "Filtro solo ore con pioggia"},
            {"command": "help", "description": "Guida completa e spiegazione"}
        ]
        try:
            self._call("setMyCommands", {"commands": commands})
        except Exception:
            pass


# ==============================================================================
# MONITOR ALLERTA PIOGGIA IMMINENTE (MULTI-PUNTO IN BACKGROUND)
# ==============================================================================
class RainAlertMonitor:
    def __init__(self, bot_runner: 'WeatherBotRunner'):
        self.bot_runner = bot_runner
        self._sent_alerts: Dict[str, float] = {}  # key: f"{chat_id}_{point_idx}_{hour_str}", val: timestamp

    def start_background_loop(self) -> None:
        def _loop() -> None:
            print(" [*] RainAlertMonitor avviato: monitoraggio pioggia multi-punto attivo.")
            time.sleep(45)  # Attesa iniziale dopo boot
            while True:
                try:
                    self.check_all_subscribed_users()
                except Exception as err:
                    print(f"[!] Errore nel monitor pioggia: {err}", file=sys.stderr)
                time.sleep(1800)  # Controlla ogni 30 minuti

        t = threading.Thread(target=_loop, daemon=True)
        t.start()

    def check_all_subscribed_users(self) -> None:
        for chat_id, alert_enabled in list(self.bot_runner.user_alerts_enabled.items()):
            if not alert_enabled:
                continue

            points = self.bot_runner.get_user_alert_points(chat_id)
            for idx, loc in enumerate(points):
                try:
                    # Usa la cache se recente invece di forzare chiamate esterne
                    data = parse_location_forecast(loc, force_refresh=False, days=1)
                    hours = data.get("hours", [])
                    local_now = data.get("local_now", datetime.now())

                    # Trova lo slot orario corrente e i successivi 3
                    upcoming_slots = [h for h in hours if h["dt"] >= local_now - timedelta(minutes=30)][:3]
                    for slot in upcoming_slots:
                        rain_mm = slot.get("rain_mm", 0.0)
                        rain_prob = slot.get("rain_prob", 0.0)

                        if rain_mm >= 0.5 or rain_prob >= 50.0:
                            alert_key = f"{chat_id}_{idx}_{slot['day']}_{slot['hour']}"
                            last_sent = self._sent_alerts.get(alert_key, 0)
                            if time.time() - last_sent > 14400:  # 4 ore di cooldown per lo stesso slot
                                self._sent_alerts[alert_key] = time.time()
                                self.send_rain_notification(chat_id, idx + 1, loc, slot)
                                break
                except Exception as e:
                    print(f"[!] Errore controllo pioggia per chat {chat_id}, punto {idx+1}: {e}", file=sys.stderr)
                time.sleep(1.5)  # Distanziamento anti-burst tra i punti

    def send_rain_notification(self, chat_id: int, point_num: int, loc: Dict[str, Any], slot: Dict[str, Any]) -> None:
        msg = [
            "⚠️ <b>ALLERTA PIOGGIA IMMINENTE</b>",
            f"📍 <b>Punto {point_num} Monitorato:</b> {loc['name']}",
            f"🕒 <b>Fascia oraria a rischio:</b> <b>{slot['day']} alle ore {slot['hour']}</b>",
            "━━━━━━━━━━━━━━━━━━━━",
            f"{slot['wmo_icon']} <b>Condizione:</b> {slot['wmo_label']}",
            f"🌧️ <b>Precipitazioni stimate:</b> <code>{slot['rain_mm']:.2f} mm</code>",
            f"🎯 <b>Probabilità di pioggia:</b> <code>{slot['rain_prob']:.0f}%</code>",
            f"🌡️ <b>Temperatura prevista:</b> <code>{slot['temp']:.1f}°C</code> (Tw <code>{slot['wet_bulb']:.1f}°C</code>)",
            f"💨 <b>Vento:</b> <code>{slot['wind_spd']:.1f} km/h</code> da <code>{slot['wind_dir']}</code>",
            "━━━━━━━━━━━━━━━━━━━━",
            "🔬 <i>Avviso automatico generato dall'Ensemble Multi-Modello (ECMWF, ICON, M-France, GFS, JMA).</i>\n"
            "<i>Per disattivare gli avvisi invia /alert_off</i>"
        ]
        try:
            self.bot_runner.client.send_message(chat_id, "\n".join(msg))
            print(f" [✓] Alert pioggia inviato con successo a chat {chat_id} per {loc['name']}.")
        except Exception as e:
            print(f" [!] Impossibile inviare notifica a chat {chat_id}: {e}", file=sys.stderr)


# ==============================================================================
# BOT CONTROLLER
# ==============================================================================
class WeatherBotRunner:
    def __init__(self, token: str):
        self.client = TelegramBotClient(token)
        self.bot_info: Dict[str, Any] = {}
        
        # Stato utente
        self.user_rain_mode: Dict[int, bool] = {}
        self.user_current_location: Dict[int, Dict[str, Any]] = {}
        self.user_current_tab: Dict[int, str] = {}
        self.user_alerts_enabled: Dict[int, bool] = {}
        
        # Configurazione 2 punti di allerta per utente: [Punto1, Punto2]
        self.user_alert_points: Dict[int, List[Dict[str, Any]]] = {}

        self.alert_monitor = RainAlertMonitor(self)

    def get_user_loc(self, chat_id: int) -> Dict[str, Any]:
        return self.user_current_location.get(chat_id, DEFAULT_LOCATIONS["putignano"])

    def get_user_alert_points(self, chat_id: int) -> List[Dict[str, Any]]:
        if chat_id not in self.user_alert_points:
            self.user_alert_points[chat_id] = [DEFAULT_LOCATIONS["putignano"], DEFAULT_LOCATIONS["monza"]]
        return self.user_alert_points[chat_id]

    def start(self) -> None:
        try:
            me_res = self.client.get_me()
            self.bot_info = me_res.get("result", {})
            bot_name = self.bot_info.get("first_name", "Meteo Ensemble Bot")
            bot_user = self.bot_info.get("username", "N/A")
            print("\n" + "=" * 65)
            print(f" 🌦️  BOT TELEGRAM CONNESSO: @{bot_user} ({bot_name})")
            print("=" * 65)
            print(" In ascolto su Telegram... Apri la chat dal tuo cellulare!")
            print(" Premi CTRL+C per arrestare.")
            print("=" * 65 + "\n")
            self.client.set_commands()
            self.alert_monitor.start_background_loop()
        except Exception as e:
            print(f"[!] Errore critico di connessione a Telegram: {e}", file=sys.stderr)
            print("[!] Verifica che il TELEGRAM_BOT_TOKEN inserito sia corretto.", file=sys.stderr)
            sys.exit(1)

        offset = 0
        while True:
            try:
                updates = self.client.get_updates(offset=offset, timeout=25)
                for u in updates:
                    offset = max(offset, u.get("update_id", 0) + 1)
                    self.handle_update(u)
            except KeyboardInterrupt:
                print("\n[✓] Arresto del bot richiesto dall'utente.")
                break
            except Exception as err:
                print(f"[!] Errore nel loop di polling: {err}", file=sys.stderr)
                time.sleep(2.0)

    def handle_update(self, update: Dict[str, Any]) -> None:
        RUNTIME_METRICS["telegram_updates"] += 1
        if "callback_query" in update:
            self.handle_callback(update["callback_query"])
            return

        if "message" in update:
            self.handle_message(update["message"])

    def handle_message(self, message: Dict[str, Any]) -> None:
        chat_id = message.get("chat", {}).get("id")
        text = (message.get("text") or "").strip()
        loc_msg = message.get("location")

        if not chat_id:
            return

        # 1. GESTIONE POSIZIONE GPS INVIATA VIA TELEGRAM (Clip -> Posizione)
        if loc_msg:
            lat = float(loc_msg.get("latitude", 0.0))
            lon = float(loc_msg.get("longitude", 0.0))
            custom_loc = {
                "key": f"gps_{lat:.4f}_{lon:.4f}",
                "name": f"📍 GPS ({lat:.3f}°N, {lon:.3f}°E)",
                "lat": lat,
                "lon": lon,
                "region": "Posizione GPS Inviata",
                "desc": f"Coordinate GPS rilevate: {lat:.4f}°N, {lon:.4f}°E"
            }
            self.user_current_location[chat_id] = custom_loc
            self.user_current_tab[chat_id] = "now"
            self.client.send_message(chat_id, f"📍 <b>Posizione GPS acquisita con successo!</b>\nCalcolo previsioni per {lat:.4f}°N, {lon:.4f}°E...")
            self.send_view(chat_id, custom_loc, "now", force_refresh=True)
            return

        low_text = text.lower()

        # 2. COMANDI STANDARD
        if low_text in ("/start", "/menu", "menu"):
            self.user_current_location[chat_id] = DEFAULT_LOCATIONS["putignano"]
            self.user_current_tab[chat_id] = "forecast"
            self.send_view(chat_id, DEFAULT_LOCATIONS["putignano"], "forecast")

        elif low_text in ("/adesso", "adesso", "/ora", "ora", "/live", "live", "/temperatura"):
            cur_loc = self.get_user_loc(chat_id)
            self.user_current_tab[chat_id] = "now"
            self.send_view(chat_id, cur_loc, "now", force_refresh=True)

        elif low_text.startswith("/mappa") or low_text.startswith("/map") or low_text.startswith("/cartina"):
            parts = text.split(maxsplit=1)
            if len(parts) > 1:
                query = parts[1]
                coords = parse_coordinates_text(query)
                if coords:
                    target_loc = coords
                else:
                    target_loc = geocode_city(query)
                    if not target_loc:
                        self.client.send_message(chat_id, f"⚠️ Impossibile trovare la città <b>'{query}'</b> per generare la mappa.")
                        return
                self.user_current_location[chat_id] = target_loc
            else:
                target_loc = self.get_user_loc(chat_id)
            self.send_map_view(chat_id, target_loc)

        elif low_text in ("/putignano", "putignano"):
            self.user_current_location[chat_id] = DEFAULT_LOCATIONS["putignano"]
            self.user_current_tab[chat_id] = "forecast"
            self.send_view(chat_id, DEFAULT_LOCATIONS["putignano"], "forecast")

        elif low_text in ("/monza", "monza"):
            self.user_current_location[chat_id] = DEFAULT_LOCATIONS["monza"]
            self.user_current_tab[chat_id] = "forecast"
            self.send_view(chat_id, DEFAULT_LOCATIONS["monza"], "forecast")

        elif low_text in ("/sinottico", "sinottico", "/editoriale", "editoriale"):
            cur_loc = self.get_user_loc(chat_id)
            self.user_current_tab[chat_id] = "synoptic"
            self.send_view(chat_id, cur_loc, "synoptic")

        elif low_text in ("/pioggia", "pioggia", "/solo-pioggia"):
            current_mode = self.user_rain_mode.get(chat_id, False)
            self.user_rain_mode[chat_id] = not current_mode
            cur_loc = self.get_user_loc(chat_id)
            cur_tab = self.user_current_tab.get(chat_id, "forecast")
            self.send_view(chat_id, cur_loc, cur_tab)

        # 3. COMANDI ALERT PIOGGIA
        elif low_text in ("/alert_on", "alert_on", "/alert on"):
            self.user_alerts_enabled[chat_id] = True
            pts = self.get_user_alert_points(chat_id)
            self.client.send_message(
                chat_id,
                "🔔 <b>Avvisi automatici di pioggia ATTIVATI!</b>\n\n"
                f"Punti monitorati in background:\n"
                f"• <b>Punto 1:</b> {pts[0]['name']}\n"
                f"• <b>Punto 2:</b> {pts[1]['name']}\n\n"
                "<i>Riceverai una notifica ogni volta che i modelli prevedono pioggia imminente (probabilità >= 50%).</i>",
                reply_markup=get_inline_keyboard(self.get_user_loc(chat_id), self.user_current_tab.get(chat_id, "forecast"), self.user_rain_mode.get(chat_id, False), True)
            )

        elif low_text in ("/alert_off", "alert_off", "/alert off"):
            self.user_alerts_enabled[chat_id] = False
            self.client.send_message(
                chat_id,
                "🔕 <b>Avvisi automatici di pioggia DISATTIVATI.</b>",
                reply_markup=get_inline_keyboard(self.get_user_loc(chat_id), self.user_current_tab.get(chat_id, "forecast"), self.user_rain_mode.get(chat_id, False), False)
            )

        elif low_text.startswith("/alert_punto1") or low_text.startswith("/alert_pos1"):
            query = text.split(maxsplit=1)[1] if len(text.split(maxsplit=1)) > 1 else ""
            if not query:
                self.client.send_message(chat_id, "ℹ️ Specifica la città o le coordinate per il Punto 1. Es:\n<code>/alert_punto1 Putignano</code> oppure <code>/alert_punto1 40.85 17.12</code>")
                return
            loc_res = resolve_location(query)
            pts = self.get_user_alert_points(chat_id)
            pts[0] = loc_res
            self.user_alert_points[chat_id] = pts
            self.client.send_message(chat_id, f"✅ <b>Punto 1 di allerta impostato su:</b>\n📍 <b>{loc_res['name']}</b> ({loc_res.get('desc', '')})")

        elif low_text.startswith("/alert_punto2") or low_text.startswith("/alert_pos2"):
            query = text.split(maxsplit=1)[1] if len(text.split(maxsplit=1)) > 1 else ""
            if not query:
                self.client.send_message(chat_id, "ℹ️ Specifica la città o le coordinate per il Punto 2. Es:\n<code>/alert_punto2 Monza</code> oppure <code>/alert_punto2 45.56 9.24</code>")
                return
            loc_res = resolve_location(query)
            pts = self.get_user_alert_points(chat_id)
            pts[1] = loc_res
            self.user_alert_points[chat_id] = pts
            self.client.send_message(chat_id, f"✅ <b>Punto 2 di allerta impostato su:</b>\n📍 <b>{loc_res['name']}</b> ({loc_res.get('desc', '')})")

        elif low_text in ("/alert_status", "alert status", "/alert"):
            status_str = "🟢 ATTIVI" if self.user_alerts_enabled.get(chat_id, False) else "🔴 DISATTIVATI"
            pts = self.get_user_alert_points(chat_id)
            self.client.send_message(
                chat_id,
                f"⚙️ <b>STATO MONITOR ALLERTA PIOGGIA:</b> {status_str}\n\n"
                f"📍 <b>Punto 1:</b> {pts[0]['name']}\n   └ <i>{pts[0].get('desc', '')}</i>\n"
                f"📍 <b>Punto 2:</b> {pts[1]['name']}\n   └ <i>{pts[1].get('desc', '')}</i>\n\n"
                "• Per cambiare il Punto 1: <code>/alert_punto1 NomeCittà</code>\n"
                "• Per cambiare il Punto 2: <code>/alert_punto2 NomeCittà</code>\n"
                "• Per attivare/spegnere: <code>/alert_on</code> o <code>/alert_off</code>"
            )

        # 4. RICERCA ESPLICITA CITTA O COORDINATE
        elif low_text.startswith("/citta ") or low_text.startswith("/cerca "):
            query = text.split(maxsplit=1)[1]
            self.execute_search_and_show(chat_id, query)

        elif low_text.startswith("/coord "):
            query = text.split(maxsplit=1)[1]
            parsed_c = parse_coordinates_text(query)
            if parsed_c:
                self.user_current_location[chat_id] = parsed_c
                self.user_current_tab[chat_id] = "now"
                self.send_view(chat_id, parsed_c, "now", force_refresh=True)
            else:
                self.client.send_message(chat_id, "⚠️ Formato coordinate non valido. Usa ad esempio:\n<code>/coord 40.8505 17.1235</code>")

        elif low_text in ("/help", "help", "guida"):
            help_text = (
                "ℹ️ <b>GUIDA METEO ENSEMBLE BOT</b>\n\n"
                "Questo bot confronta in tempo reale 5 modelli meteorologici mondiali:\n"
                "• <b>ECMWF IFS (UE)</b> • <b>DWD ICON-EU (DE)</b> • <b>Météo-France (FR)</b>\n"
                "• <b>GFS Global (USA)</b> • <b>JMA Seamless (JP)</b>\n\n"
                "🔍 <b>Ricerca Città & Posizione GPS:</b>\n"
                "• Scrivi il nome di qualsiasi città (es. <code>Roma</code>, <code>Bari</code>, <code>Milano</code>) o usa <code>/citta Firenze</code>.\n"
                "• Invia la tua posizione GPS toccando la graffetta 📎 -> <b>Posizione</b>.\n"
                "• Oppure digita direttamente le coordinate: <code>40.8505, 17.1235</code>.\n\n"
                "🔔 <b>Allerta Pioggia Multi-Punto:</b>\n"
                "• <code>/alert_on</code> e <code>/alert_off</code> per attivare o spegnere gli avvisi.\n"
                "• <code>/alert_punto1 Putignano</code> e <code>/alert_punto2 Monza</code> per configurare i 2 punti da monitorare.\n\n"
                "Usa i pulsanti sotto per navigare:"
            )
            cur_loc = self.get_user_loc(chat_id)
            self.client.send_message(
                chat_id,
                help_text,
                reply_markup=get_inline_keyboard(cur_loc, "forecast", self.user_rain_mode.get(chat_id, False), self.user_alerts_enabled.get(chat_id, False))
            )
        else:
            # Prova a interpretare il messaggio dell'utente come città o coordinate
            coords = parse_coordinates_text(text)
            if coords:
                self.user_current_location[chat_id] = coords
                self.user_current_tab[chat_id] = "now"
                self.send_view(chat_id, coords, "now", force_refresh=True)
            else:
                geocoded = geocode_city(text)
                if geocoded:
                    self.user_current_location[chat_id] = geocoded
                    self.user_current_tab[chat_id] = "forecast"
                    self.send_view(chat_id, geocoded, "forecast")
                else:
                    cur_loc = self.get_user_loc(chat_id)
                    self.send_view(chat_id, cur_loc, "forecast")

    def execute_search_and_show(self, chat_id: int, query: str) -> None:
        geocoded = geocode_city(query)
        if geocoded:
            self.user_current_location[chat_id] = geocoded
            self.user_current_tab[chat_id] = "forecast"
            self.send_view(chat_id, geocoded, "forecast")
        else:
            self.client.send_message(
                chat_id,
                f"⚠️ Impossibile trovare la città <b>'{query}'</b>. Prova a verificare l'ortografia o a inviare le coordinate numeriche."
            )

    def handle_callback(self, cb: Dict[str, Any]) -> None:
        cb_id = cb.get("id")
        data = cb.get("data", "")
        message = cb.get("message", {})
        chat_id = message.get("chat", {}).get("id")
        message_id = message.get("message_id")

        if not chat_id or not message_id:
            return

        force_refresh = False
        cur_loc = self.get_user_loc(chat_id)
        cur_tab = self.user_current_tab.get(chat_id, "forecast")
        cur_rain = self.user_rain_mode.get(chat_id, False)

        if data.startswith("loc_"):
            loc_key = data.split("_")[1]
            if loc_key in DEFAULT_LOCATIONS:
                cur_loc = DEFAULT_LOCATIONS[loc_key]
                self.user_current_location[chat_id] = cur_loc
            self.client.answer_callback_query(cb_id, text=f"Selezionato: {cur_loc['name']}")

        elif data.startswith("tab_"):
            target_tab = data.split("_")[2]
            cur_tab = target_tab
            self.user_current_tab[chat_id] = cur_tab
            if cur_tab == "now":
                force_refresh = True
            self.client.answer_callback_query(cb_id, text=f"Scheda: {cur_tab.capitalize()}")

        elif data.startswith("refresh_"):
            force_refresh = True
            self.client.answer_callback_query(cb_id, text="Aggiornamento modelli live...")

        elif data == "toggle_rain_on":
            self.user_rain_mode[chat_id] = True
            cur_rain = True
            self.client.answer_callback_query(cb_id, text="Filtro Solo Pioggia ATTIVATO")

        elif data == "toggle_rain_off":
            self.user_rain_mode[chat_id] = False
            cur_rain = False
            self.client.answer_callback_query(cb_id, text="Filtro Solo Pioggia DISATTIVATO")

        elif data == "toggle_alert_on":
            self.user_alerts_enabled[chat_id] = True
            self.client.answer_callback_query(cb_id, text="Allerta Pioggia ATTIVATA")

        elif data == "toggle_alert_off":
            self.user_alerts_enabled[chat_id] = False
            self.client.answer_callback_query(cb_id, text="Allerta Pioggia DISATTIVATA")

        elif data == "help_search":
            self.client.answer_callback_query(cb_id)
            self.client.send_message(
                chat_id,
                "🔍 <b>COME CERCARE QUALSIASI CITTÀ O INVIARE LA POSIZIONE:</b>\n\n"
                "1. <b>Nome Città:</b> Scrivi semplicemente il nome in chat (es. <code>Bari</code>, <code>Roma</code>, <code>Napoli</code>).\n"
                "2. <b>Posizione GPS:</b> Tocca l'icona 📎 (graffetta) -> <b>Posizione</b> per inviare la tua posizione esatta.\n"
                "3. <b>Coordinate Numeriche:</b> Invia latitudine e longitudine (es. <code>40.8505, 17.1235</code>).\n"
                "4. <b>Mappa Grafica:</b> Usa <code>/mappa</code> o premi il pulsante 🗺️ Mappa per ricevere l'immagine satellitare/radar."
            )
            return

        elif data.startswith("show_map"):
            self.client.answer_callback_query(cb_id, text="Generazione mappa in corso...")
            self.send_map_view(chat_id, cur_loc)
            return

        self.update_view(chat_id, message_id, cur_loc, cur_tab, cur_rain, force_refresh=force_refresh)

    def send_map_view(self, chat_id: int, loc: Dict[str, Any]) -> None:
        """Genera e invia l'immagine statica PNG con la mappa di sfondo e le schede meteo/pioggia."""
        try:
            data = parse_location_forecast(loc, force_refresh=True)
            png_bytes = generate_static_weather_map(loc, data)
            
            if not png_bytes:
                self.client.send_message(chat_id, "⚠️ Impossibile generare l'immagine della mappa (libreria Pillow non disponibile).")
                return

            m = data.get("metrics", {})
            caption = (
                f"🗺️ <b>Mappa Meteo Statica • {loc['name']}</b>\n"
                f"📍 <code>{loc['lat']:.4f}°N, {loc['lon']:.4f}°E</code>\n\n"
                f"🌡️ <b>Temperatura Live:</b> <code>{m.get('current_temp', 0):.1f}°C</code>\n"
                f"🌧️ <b>Pioggia stimata 24h:</b> <code>{m.get('total_rain', 0):.1f} mm</code> (Prob. max <code>{m.get('max_rain_prob', 0):.0f}%</code>)\n"
                f"🕒 <i>Aggiornato alle {data.get('updated_at', '')} • Open-Meteo & OSM</i>"
            )
            only_rain = self.user_rain_mode.get(chat_id, False)
            alert_on = self.user_alerts_enabled.get(chat_id, False)
            markup = get_inline_keyboard(loc, "map", only_rain, alert_on)
            self.client.send_photo(chat_id, png_bytes, caption=caption, reply_markup=markup)
        except Exception as e:
            print(f"[!] Errore durante l'invio della mappa a chat {chat_id}: {e}", file=sys.stderr)
            self.client.send_message(chat_id, f"⚠️ Errore nella generazione della mappa:\n<code>{str(e)}</code>")

    def get_content_for_view(self, loc: Dict[str, Any], tab: str, only_rain: bool = False, force_refresh: bool = False) -> str:
        data = parse_location_forecast(loc, force_refresh=force_refresh)
        if tab == "now":
            return format_current_weather_message(data)
        elif tab == "synoptic":
            return format_single_city_synoptic_message(data, loc["key"])
        else:
            return format_city_weather_message(data, only_rain=only_rain)

    def send_view(self, chat_id: int, loc: Dict[str, Any], tab: str, force_refresh: bool = False) -> None:
        try:
            only_rain = self.user_rain_mode.get(chat_id, False)
            alert_on = self.user_alerts_enabled.get(chat_id, False)
            text = self.get_content_for_view(loc, tab, only_rain=only_rain, force_refresh=force_refresh)
            self.client.send_message(chat_id, text, reply_markup=get_inline_keyboard(loc, tab, only_rain, alert_on))
        except Exception as e:
            self.client.send_message(
                chat_id,
                f"⚠️ <b>Errore nel recupero dati meteo:</b>\n<code>{str(e)}</code>"
            )

    def update_view(self, chat_id: int, message_id: int, loc: Dict[str, Any], tab: str, only_rain: bool, force_refresh: bool = False) -> None:
        try:
            text = self.get_content_for_view(loc, tab, only_rain=only_rain, force_refresh=force_refresh)
            alert_on = self.user_alerts_enabled.get(chat_id, False)
            self.client.edit_message_text(chat_id, message_id, text, reply_markup=get_inline_keyboard(loc, tab, only_rain, alert_on))
        except Exception as e:
            err_msg = str(e)
            if "message is not modified" not in err_msg.lower():
                try:
                    alert_on = self.user_alerts_enabled.get(chat_id, False)
                    self.client.edit_message_text(
                        chat_id, message_id,
                        f"⚠️ <b>Errore durante l'aggiornamento:</b>\n<code>{err_msg}</code>",
                        reply_markup=get_inline_keyboard(loc, tab, only_rain, alert_on)
                    )
                except Exception:
                    pass


# ==============================================================================
# STATO GLOBALE E METRICHE DI RUNTIME
# ==============================================================================
APP_START_TIME = time.time()
RUNTIME_METRICS = {
    "http_requests": 0,
    "telegram_updates": 0,
    "last_ping_time": None,
    "last_ping_status": None,
    "pings_sent": 0
}

# ==============================================================================
# HTTP HEALTH-CHECK SERVER (PER RENDER / CLOUD WEB SERVICE PORT BINDING)
# ==============================================================================
class HealthCheckHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        pass

    def _get_uptime_str(self) -> str:
        uptime_sec = int(time.time() - APP_START_TIME)
        hours, rem = divmod(uptime_sec, 3600)
        minutes, seconds = divmod(rem, 60)
        return f"{hours}h {minutes}m {seconds}s"

    def do_HEAD(self) -> None:
        RUNTIME_METRICS["http_requests"] += 1
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()

    def do_GET(self) -> None:
        RUNTIME_METRICS["http_requests"] += 1
        parsed_path = urllib.parse.urlparse(self.path).path

        if parsed_path in ("/health", "/healthz", "/ping", "/status", "/json"):
            payload = json.dumps({
                "status": "HEALTHY",
                "service": "meteo-ensemble-telegram-bot",
                "uptime": self._get_uptime_str(),
                "uptime_seconds": int(time.time() - APP_START_TIME),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "http_requests_received": RUNTIME_METRICS["http_requests"],
                "telegram_updates_handled": RUNTIME_METRICS["telegram_updates"],
                "last_keep_alive_ping": RUNTIME_METRICS["last_ping_time"],
                "last_ping_status": RUNTIME_METRICS["last_ping_status"]
            }, indent=2).encode("utf-8")

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.end_headers()
            self.wfile.write(payload)
            return

        uptime_str = self._get_uptime_str()
        ping_status = RUNTIME_METRICS["last_ping_status"] or "In attesa"

        html = f"""<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Meteo Ensemble Bot - Status</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            background: #090d16;
            color: #f0f3f8;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            padding: 20px;
        }}
        .card {{
            background: #131b2e;
            border: 1px solid #1e293b;
            border-radius: 16px;
            padding: 32px;
            max-width: 520px;
            width: 100%;
            box-shadow: 0 10px 30px rgba(0,0,0,0.5);
            text-align: center;
        }}
        .badge {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: rgba(16, 185, 129, 0.15);
            color: #10b981;
            padding: 6px 14px;
            border-radius: 999px;
            font-weight: 600;
            font-size: 0.85rem;
            margin-bottom: 16px;
            border: 1px solid rgba(16, 185, 129, 0.3);
        }}
        .badge::before {{
            content: "";
            width: 8px;
            height: 8px;
            background: #10b981;
            border-radius: 50%;
            box-shadow: 0 0 8px #10b981;
        }}
        h1 {{
            color: #ffffff;
            font-size: 1.5rem;
            margin-bottom: 8px;
        }}
        h1 span {{ color: #38bdf8; }}
        p.subtitle {{
            color: #8b9bb4;
            font-size: 0.95rem;
            margin-bottom: 24px;
        }}
        .stats-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 12px;
            text-align: left;
            margin-bottom: 24px;
        }}
        .stat-box {{
            background: #0d1322;
            padding: 12px 16px;
            border-radius: 10px;
            border: 1px solid #1e293b;
        }}
        .stat-label {{
            font-size: 0.75rem;
            color: #8b9bb4;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 4px;
        }}
        .stat-value {{
            font-size: 0.95rem;
            font-weight: 600;
            color: #f0f3f8;
            word-break: break-all;
        }}
        .footer-note {{
            font-size: 0.8rem;
            color: #64748b;
            border-top: 1px solid #1e293b;
            padding-top: 16px;
        }}
        code {{
            background: #1e293b;
            color: #38bdf8;
            padding: 2px 6px;
            border-radius: 4px;
            font-family: monospace;
            font-size: 0.85rem;
        }}
    </style>
</head>
<body>
    <div class="card">
        <div class="badge">ONLINE &amp; ACTIVE 24/7</div>
        <h1>🌦️ Meteo <span>Ensemble Bot</span></h1>
        <p class="subtitle">5 Modelli &bull; Geocoding &bull; GPS &bull; Alert Pioggia</p>
        
        <div class="stats-grid">
            <div class="stat-box">
                <div class="stat-label">Uptime Servizio</div>
                <div class="stat-value">{uptime_str}</div>
            </div>
            <div class="stat-box">
                <div class="stat-label">Port Binding</div>
                <div class="stat-value" style="color: #10b981;">Attivo (Port {self.server.server_port})</div>
            </div>
            <div class="stat-box">
                <div class="stat-label">Aggiornamenti Bot</div>
                <div class="stat-value">{RUNTIME_METRICS['telegram_updates']} processati</div>
            </div>
            <div class="stat-box">
                <div class="stat-label">Keep-Alive Ping</div>
                <div class="stat-value" style="color: #38bdf8;">{ping_status}</div>
            </div>
        </div>

        <div class="footer-note">
            Render Keep-Alive attivo. Endpoint monitor: <code>/health</code>
        </div>
    </div>
</body>
</html>
"""
        response_bytes = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(response_bytes)))
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(response_bytes)


def start_health_check_server(port: int = 8080) -> None:
    try:
        server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        print(f" [*] Health-check HTTP Server attivo su porta {port} (Web Service Port Binding OK).")
    except Exception as e:
        print(f" [!] Avviso: Impossibile avviare il server HTTP health-check: {e}")


def start_keep_alive_pinger(target_url: str, interval_seconds: int = 540) -> None:
    if not target_url or not target_url.startswith("http"):
        print(" [i] Keep-Alive Pinger: Nessun URL esterno configurato (modalità locale attiva).")
        return

    clean_url = target_url.rstrip("/")
    ping_endpoint = f"{clean_url}/health"

    def _ping_loop() -> None:
        print(f" [*] Keep-Alive Pinger avviato -> Target: {ping_endpoint} (ogni {interval_seconds // 60} min)")
        time.sleep(30)
        while True:
            try:
                req = urllib.request.Request(
                    ping_endpoint,
                    headers={
                        "User-Agent": "Meteo-Bot-KeepAlive/1.0",
                        "Accept": "application/json"
                    }
                )
                with urllib.request.urlopen(req, timeout=20) as resp:
                    code = resp.getcode()
                    now_str = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
                    RUNTIME_METRICS["pings_sent"] += 1
                    RUNTIME_METRICS["last_ping_time"] = now_str
                    RUNTIME_METRICS["last_ping_status"] = f"HTTP {code} OK ({now_str})"
                    print(f" [✓] Keep-Alive Ping inviato ({now_str}) -> HTTP {code}")
            except Exception as err:
                now_str = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
                RUNTIME_METRICS["last_ping_time"] = now_str
                RUNTIME_METRICS["last_ping_status"] = f"Errore: {err}"
                print(f" [!] Keep-Alive Ping fallito ({now_str}): {err}")

            time.sleep(interval_seconds)

    pinger_thread = threading.Thread(target=_ping_loop, daemon=True)
    pinger_thread.start()


# ==============================================================================
# ENTRY POINT
# ==============================================================================
def main() -> None:
    port_env = os.environ.get("PORT")
    port = int(port_env) if port_env and port_env.isdigit() else 8080
    start_health_check_server(port)

    target_url = (
        os.environ.get("RENDER_EXTERNAL_URL") or
        os.environ.get("PING_URL") or
        ""
    )
    interval_env = os.environ.get("KEEP_ALIVE_INTERVAL")
    interval = int(interval_env) if interval_env and interval_env.isdigit() else 540
    start_keep_alive_pinger(target_url, interval_seconds=interval)

    parser = argparse.ArgumentParser(description="Meteo Ensemble - Telegram Bot")
    parser.add_argument("--token", "-t", default=None, help="Telegram Bot Token (oppure usa variabile d'ambiente TELEGRAM_BOT_TOKEN)")
    args = parser.parse_args()

    token = args.token or os.environ.get("TELEGRAM_BOT_TOKEN")

    if not token:
        print("\n" + "=" * 65)
        print(" 🌦️  CONFIGURAZIONE TELEGRAM BOT TOKEN")
        print("=" * 65)
        print(" Non è stato trovato alcun Token Telegram.")
        print(" Puoi ottenerne uno GRATIS in 30 secondi:")
        print("  1. Apri Telegram e cerca @BotFather")
        print("  2. Invia /newbot e assegna un nome (es. 'MeteoEnsembleBot')")
        print("  3. Copia la stringa di Token rilasciata (es. 123456:ABC-DEF...)")
        print("=" * 65)
        try:
            token = input("\nIncolla qui il tuo TELEGRAM_BOT_TOKEN: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nOperazione annullata.")
            sys.exit(0)

    if not token:
        print("[!] Token non valido. Chiusura.", file=sys.stderr)
        sys.exit(1)

    runner = WeatherBotRunner(token)
    runner.start()


if __name__ == "__main__":
    main()
