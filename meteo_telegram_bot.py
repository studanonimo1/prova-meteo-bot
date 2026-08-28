#!/usr/bin/env python3
"""
Meteo Multi-Modello (Putignano & Monza) - Standalone Telegram Bot (Zero External Dependencies)
Bot Telegram completo per previsioni meteo ed ensemble di 5 modelli internazionali.
Utilizza esclusivamente la libreria standard Python (urllib, json, threading, http.server)
ed è ottimizzato per l'esecuzione locale e il deploy gratuito 24/7 su Cloud (Render, Railway, Koyeb).
"""

import sys
import os
import math
import json
import time
import argparse
import threading
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple, Union
from http.server import HTTPServer, BaseHTTPRequestHandler

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
CACHE_TTL_SECONDS = 600  # 10 minuti di cache per chiamate meteo
HTTP_TIMEOUT = 25
MAX_RETRIES = 3
BASE_RETRY_DELAY = 1.0

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
# CACHE MANAGER THREAD-SAFE
# ==============================================================================
class CacheManager:
    def __init__(self, ttl_seconds: int = CACHE_TTL_SECONDS):
        self.ttl = ttl_seconds
        self._cache: Dict[str, Dict[str, Any]] = {}
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

    def clear(self, key: Optional[str] = None) -> None:
        with self._lock:
            if key:
                self._cache.pop(key, None)
            else:
                self._cache.clear()

cache_store = CacheManager()

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
    """Interroga l'API Open-Meteo Multi-Modello con la sola standard library urllib."""
    models_query = ",".join(MODELS.keys())
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        f"&hourly=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m,wind_direction_10m,precipitation,precipitation_probability"
        f"&models={models_query}"
        f"&forecast_days={forecast_days}"
        f"&timezone=auto"
    )

    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Meteo-Telegram-Bot/1.0"}
    )
    for attempt in range(MAX_RETRIES):
        try:
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"HTTP {resp.status}")
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            if attempt == MAX_RETRIES - 1:
                raise RuntimeError(f"Errore connessione Open-Meteo: {e}") from e
            time.sleep(BASE_RETRY_DELAY * (attempt + 1))
    raise RuntimeError("Chiamata Open-Meteo fallita.")


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
        "max_temp": max(all_temps) if all_temps else 0.0,
        "min_temp": min(all_temps) if all_temps else 0.0,
        "avg_temp": sum(all_temps) / len(all_temps) if all_temps else 0.0,
        "max_wb": max(all_wbs) if all_wbs else 0.0,
        "total_rain": sum(all_precips) if all_precips else 0.0,
        "max_rain_prob": max(all_probs) if all_probs else 0.0,
        "days": days_data
    }


def parse_location_forecast(loc_key: str, force_refresh: bool = False, days: int = 3) -> Dict[str, Any]:
    """Ottiene i dati meteo con cache in memoria per una località."""
    loc_info = LOCATIONS.get(loc_key)
    if not loc_info:
        raise ValueError(f"Località '{loc_key}' non supportata.")

    cache_key = f"meteo_{loc_key}_{days}"
    if not force_refresh:
        cached = cache_store.get(cache_key)
        if cached:
            return cached

    raw_data = fetch_weather_data(lat=loc_info["lat"], lon=loc_info["lon"], forecast_days=days)
    metrics = extract_city_metrics(raw_data)

    hourly = raw_data.get("hourly", {})
    times = hourly.get("time", [])

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
            "day": day_str,
            "hour": hour_str,
            "temp": avg_temp,
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
        "updated_at": datetime.now().strftime("%d/%m/%Y alle %H:%M")
    }

    cache_store.set(cache_key, result_data)
    return result_data


# ==============================================================================
# FORMATTAZIONE MESSAGGI TELEGRAM
# ==============================================================================
def format_city_weather_message(data: Dict[str, Any], only_rain: bool = False) -> str:
    loc = data["loc"]
    daily = data["daily"]
    updated_at = data.get("updated_at", "")

    header = [
        f"📍 <b>PREVISIONI METEO ENSEMBLE</b>",
        f"🏙️ <b>{loc['name'].upper()}</b> (<i>{loc['region']}</i>)",
        f"🔬 <i>5 Modelli: ECMWF, ICON, M-France, GFS, JMA</i>",
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
        model_str = " • ".join([f"{MODELS[k]}: <code>{stats['model_totals'][k]:.1f}mm</code>" for k in MODELS.keys()])
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
        f"🕒 <i>Aggiornato alle {updated_at} • Dati Open-Meteo</i>"
    ]

    return "\n\n".join(["\n".join(header), "\n\n".join(body), "\n".join(footer)])


def format_synoptic_editorial_message(put_data: Dict[str, Any], mon_data: Dict[str, Any]) -> str:
    now_str = datetime.now().strftime("%d/%m/%Y alle %H:%M")
    m_put = put_data.get("metrics", {})
    m_mon = mon_data.get("metrics", {})

    max_t_p = m_put.get("max_temp", 35.0)
    tot_r_p = m_put.get("total_rain", 0.0)
    max_wb_p = m_put.get("max_wb", 22.0)

    max_t_m = m_mon.get("max_temp", 30.0)
    tot_r_m = m_mon.get("total_rain", 0.0)
    max_pr_m = m_mon.get("max_rain_prob", 0.0)
    max_wb_m = m_mon.get("max_wb", 23.5)

    out = [
        "📡 <b>QUADRO SINOTTICO & EDITORIALE SPECIALISTICO</b>",
        "<i>Analisi multi-modello comparata Nord vs Sud</i>",
        "━━━━━━━━━━━━━━━━━━━━",
        "🔥 <b>TITOLO SINOTTICO:</b>",
        "<b>Dicotomia atmosferica: pulsazione calda subtropicale al Sud e marcati contrasti termici con rottura instabile al Nord.</b>\n",
        "🧭 <b>INQUADRAMENTO GENERALE:</b>",
        "L'espansione dell'anticiclone subtropicale continentale favorisce un sensibile richiamo caldo nordafricano sul versante adriatico e meridionale. "
        "Al contempo, il cedimento del geopotenziale espone l'alta Pianura Padana e la Brianza a flussi più freschi e instabili di matrice atlantica.\n",
        f"📍 <b>FOCUS PUTIGNANO (BA) & ADRIATICO:</b>",
        f"• Picco termico: <code>{max_t_p:.1f}°C</code> (fino a 5-8°C oltre le medie).",
        f"• Bulbo Umido max: <code>{max_wb_p:.1f}°C</code> (caldo asciutto e ventilato).",
        f"• Precipitazioni totali 3 giorni: <code>{tot_r_p:.1f} mm</code> (stabilità predominante).\n",
        f"📍 <b>FOCUS MONZA & ALTA PIANURA PADANA:</b>",
        f"• Massime fino a <code>{max_t_m:.1f}°C</code> con elevata afa prefrontale.",
        f"• Bulbo Umido max: <code>{max_wb_m:.1f}°C</code> (indice di afa percepita).",
        f"• Pioggia cumulata: <code>{tot_r_m:.1f} mm</code> (picco probabilità <code>{max_pr_m:.0f}%</code> con rischio temporali forti).\n",
        "━━━━━━━━━━━━━━━━━━━━",
        f"🕒 <i>Aggiornato alle {now_str} • Meteo Ensemble Bot</i>"
    ]
    return "\n".join(out)


def get_inline_keyboard(current_view: str = "putignano", only_rain: bool = False) -> Dict[str, Any]:
    put_label = "👉 📍 Putignano" if current_view == "putignano" else "📍 Putignano"
    mon_label = "👉 📍 Monza" if current_view == "monza" else "📍 Monza"
    syn_label = "👉 📡 Sinottico" if current_view == "sinottico" else "📡 Sinottico"
    rain_label = "🌧️ Solo Pioggia (ATTIVO)" if only_rain else "🌧️ Solo Pioggia"

    return {
        "inline_keyboard": [
            [
                {"text": put_label, "callback_data": "view_putignano"},
                {"text": mon_label, "callback_data": "view_monza"}
            ],
            [
                {"text": syn_label, "callback_data": "view_sinottico"},
                {"text": rain_label, "callback_data": f"toggle_rain_{'off' if only_rain else 'on'}"}
            ],
            [
                {"text": "🔄 Aggiorna Dati Live", "callback_data": f"refresh_{current_view}"}
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

    def set_commands(self) -> None:
        commands = [
            {"command": "start", "description": "Apri il menu meteo principale"},
            {"command": "putignano", "description": "Previsioni 3 giorni per Putignano (BA)"},
            {"command": "monza", "description": "Previsioni 3 giorni per Monza"},
            {"command": "sinottico", "description": "Quadro sinottico specialistico ed editoriale"},
            {"command": "pioggia", "description": "Filtro solo ore con pioggia"},
            {"command": "help", "description": "Guida ai modelli e all'uso"}
        ]
        try:
            self._call("setMyCommands", {"commands": commands})
        except Exception:
            pass


# ==============================================================================
# BOT CONTROLLER
# ==============================================================================
class WeatherBotRunner:
    def __init__(self, token: str):
        self.client = TelegramBotClient(token)
        self.bot_info: Dict[str, Any] = {}
        # Mantiene per ogni utente/chat lo stato "solo_pioggia" (default False)
        self.user_rain_mode: Dict[int, bool] = {}
        self.user_current_view: Dict[int, str] = {}

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
        text = (message.get("text") or "").strip().lower()

        if not chat_id:
            return

        if text in ("/start", "/menu", "menu"):
            self.user_current_view[chat_id] = "putignano"
            self.send_view(chat_id, "putignano")
        elif text in ("/putignano", "putignano"):
            self.user_current_view[chat_id] = "putignano"
            self.send_view(chat_id, "putignano")
        elif text in ("/monza", "monza"):
            self.user_current_view[chat_id] = "monza"
            self.send_view(chat_id, "monza")
        elif text in ("/sinottico", "sinottico", "/editoriale", "editoriale"):
            self.user_current_view[chat_id] = "sinottico"
            self.send_view(chat_id, "sinottico")
        elif text in ("/pioggia", "pioggia", "/solo-pioggia"):
            current_mode = self.user_rain_mode.get(chat_id, False)
            self.user_rain_mode[chat_id] = not current_mode
            cur_view = self.user_current_view.get(chat_id, "putignano")
            self.send_view(chat_id, cur_view)
        elif text in ("/help", "help", "guida"):
            help_text = (
                "ℹ️ <b>GUIDA METEO ENSEMBLE BOT</b>\n\n"
                "Questo bot aggrega in tempo reale 5 modelli meteorologici mondiali:\n"
                "• <b>ECMWF IFS:</b> Modello Europeo (alta precisione)\n"
                "• <b>DWD ICON-EU:</b> Modello Tedesco ad alta risoluzione\n"
                "• <b>Météo-France:</b> Modello Francese Seamless\n"
                "• <b>GFS Global:</b> Modello Statunitense NOAA\n"
                "• <b>JMA:</b> Modello Giapponese\n\n"
                "🌡️ <b>Bulbo Umido (Wet Bulb):</b> Calcolato con la formula di Stull, misura lo stress termico combinando temperatura e umidità.\n\n"
                "Tocca un pulsante sotto per visualizzare le previsioni:"
            )
            self.client.send_message(
                chat_id,
                help_text,
                reply_markup=get_inline_keyboard("putignano", self.user_rain_mode.get(chat_id, False))
            )
        else:
            self.send_view(chat_id, "putignano")

    def handle_callback(self, cb: Dict[str, Any]) -> None:
        cb_id = cb.get("id")
        data = cb.get("data", "")
        message = cb.get("message", {})
        chat_id = message.get("chat", {}).get("id")
        message_id = message.get("message_id")

        if not chat_id or not message_id:
            return

        force_refresh = False
        cur_view = self.user_current_view.get(chat_id, "putignano")
        cur_rain = self.user_rain_mode.get(chat_id, False)

        if data.startswith("view_"):
            cur_view = data.replace("view_", "")
            self.user_current_view[chat_id] = cur_view
            self.client.answer_callback_query(cb_id, text=f"Caricamento {cur_view.capitalize()}...")
        elif data.startswith("refresh_"):
            cur_view = data.replace("refresh_", "")
            self.user_current_view[chat_id] = cur_view
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

        self.update_view(chat_id, message_id, cur_view, cur_rain, force_refresh=force_refresh)

    def get_content_for_view(self, view: str, only_rain: bool = False, force_refresh: bool = False) -> str:
        if view == "sinottico":
            p_data = parse_location_forecast("putignano", force_refresh=force_refresh)
            m_data = parse_location_forecast("monza", force_refresh=force_refresh)
            return format_synoptic_editorial_message(p_data, m_data)
        elif view in ("monza", "putignano"):
            data = parse_location_forecast(view, force_refresh=force_refresh)
            return format_city_weather_message(data, only_rain=only_rain)
        else:
            data = parse_location_forecast("putignano", force_refresh=force_refresh)
            return format_city_weather_message(data, only_rain=only_rain)

    def send_view(self, chat_id: int, view: str) -> None:
        try:
            only_rain = self.user_rain_mode.get(chat_id, False)
            text = self.get_content_for_view(view, only_rain=only_rain, force_refresh=False)
            self.client.send_message(chat_id, text, reply_markup=get_inline_keyboard(view, only_rain))
        except Exception as e:
            self.client.send_message(
                chat_id,
                f"⚠️ <b>Errore nel recupero dati meteo:</b>\n<code>{str(e)}</code>",
                reply_markup=get_inline_keyboard(view, self.user_rain_mode.get(chat_id, False))
            )

    def update_view(self, chat_id: int, message_id: int, view: str, only_rain: bool, force_refresh: bool = False) -> None:
        try:
            text = self.get_content_for_view(view, only_rain=only_rain, force_refresh=force_refresh)
            self.client.edit_message_text(chat_id, message_id, text, reply_markup=get_inline_keyboard(view, only_rain))
        except Exception as e:
            err_msg = str(e)
            if "message is not modified" not in err_msg.lower():
                try:
                    self.client.edit_message_text(
                        chat_id, message_id,
                        f"⚠️ <b>Errore durante l'aggiornamento:</b>\n<code>{err_msg}</code>",
                        reply_markup=get_inline_keyboard(view, only_rain)
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
        # Silenzia i log interni HTTP
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

        # Endpoint JSON per UptimeRobot / cron / status
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

        # Dashboard HTML
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
        <p class="subtitle">Putignano &bull; Monza &bull; 5 Modelli Multi-Forecast</p>
        
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
    """Avvia un server HTTP leggero in un thread demone per soddisfare il port scan di Render/Koyeb."""
    try:
        server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        print(f" [*] Health-check HTTP Server attivo su porta {port} (Web Service Port Binding OK).")
    except Exception as e:
        print(f" [!] Avviso: Impossibile avviare il server HTTP health-check: {e}")


def start_keep_alive_pinger(target_url: str, interval_seconds: int = 540) -> None:
    """Invia richieste periodiche GET all'endpoint di monitoraggio per prevenire lo sleep su Render Free."""
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
    # 1. Avvio server HTTP in background per Render ($PORT)
    port_env = os.environ.get("PORT")
    port = int(port_env) if port_env and port_env.isdigit() else 8080
    start_health_check_server(port)

    # 2. Configura e avvia il Keep-Alive Pinger automatico
    target_url = (
        os.environ.get("RENDER_EXTERNAL_URL") or
        os.environ.get("PING_URL") or
        ""
    )
    interval_env = os.environ.get("KEEP_ALIVE_INTERVAL")
    interval = int(interval_env) if interval_env and interval_env.isdigit() else 540
    start_keep_alive_pinger(target_url, interval_seconds=interval)

    # 3. Parsing argomenti e token Telegram
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
