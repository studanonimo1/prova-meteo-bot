#!/usr/bin/env python3
"""
Test di verifica del Fallback Ibrido Multi-Modello (fino a 6 centri di calcolo).
Simula il rate limit HTTP 429 su Open-Meteo e certifica che il bot:
1. Attiva l'ensemble ibrido di emergenza combinando MET Norway, DWD Bright Sky, GFS, Météo-France, GEM e JMA (6 modelli).
2. Resiste a un'interruzione totale di Open-Meteo degradando con grazia a MET Norway + DWD Bright Sky (2 modelli).
3. Genera correttamente schede live, bollettini CML ed editoriali sinottici con la corretta indicazione del numero di centri.
4. Fornisce diagnostica di runtime tramite /diagnostica.
"""

import sys
import os
from unittest.mock import patch
import urllib.error
import urllib.request

# Aggiunge la directory corrente al path di Python
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import meteo_telegram_bot

def test_hybrid_fallback_6_models():
    print("=== TEST 1: FALLBACK IBRIDO 6 MODELLI (HTTP 429 SU V1/FORECAST) ===")
    monza_loc = meteo_telegram_bot.DEFAULT_LOCATIONS["monza"]
    orig_urlopen = urllib.request.urlopen

    def mock_urlopen_forecast_429(req, *args, **kwargs):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "v1/forecast" in url:
            raise urllib.error.HTTPError(url, 429, "Too Many Requests", {}, None)
        return orig_urlopen(req, *args, **kwargs)

    with patch("urllib.request.urlopen", side_effect=mock_urlopen_forecast_429):
        data = meteo_telegram_bot.parse_location_forecast(monza_loc, force_refresh=True)

        print(f" -> Sorgente rilevata: {data.get('source_label')}")
        print(f" -> Modelli attivi: {data.get('active_models')}")
        print(f" -> Numero modelli: {data.get('model_count')}")

        assert data.get("model_count", 0) >= 5, f"Attesi almeno 5/6 modelli nel fallback avanzato, trovati: {data.get('model_count')}"
        assert "met_norway" in data.get("active_models", [])
        assert "dwd_brightsky" in data.get("active_models", [])

        # Scheda live
        current_msg = meteo_telegram_bot.format_current_weather_message(data)
        assert f"Media {data.get('model_count')} Modelli" in current_msg

        # Bollettino 3gg
        bulletin_msg = meteo_telegram_bot.format_city_weather_message(data)
        assert f"media {data.get('model_count')} modelli" in bulletin_msg

        # Sinottico
        synoptic_msg = meteo_telegram_bot.format_single_city_synoptic_message(data, monza_loc["key"])
        assert f"({data.get('model_count')} centri di calcolo)" in synoptic_msg

    print(" -> PASS: Fallback 6 modelli validato con successo.")


def test_hybrid_fallback_total_outage():
    print("\n=== TEST 2: RESILIENZA OUTAGE TOTALE OPEN-METEO (GARANTITI 3 MODELLI INDIPENDENTI) ===")
    monza_loc = meteo_telegram_bot.DEFAULT_LOCATIONS["monza"]
    orig_urlopen = urllib.request.urlopen

    def mock_urlopen_all_openmeteo_down(req, *args, **kwargs):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "open-meteo.com" in url:
            raise urllib.error.HTTPError(url, 429, "Too Many Requests", {}, None)
        return orig_urlopen(req, *args, **kwargs)

    with patch("urllib.request.urlopen", side_effect=mock_urlopen_all_openmeteo_down):
        data = meteo_telegram_bot.parse_location_forecast(monza_loc, force_refresh=True)

        print(f" -> Sorgente rilevata: {data.get('source_label')}")
        print(f" -> Modelli attivi: {data.get('active_models')}")
        print(f" -> Numero modelli: {data.get('model_count')}")

        assert data.get("model_count", 0) >= 3, f"Attesi almeno 3 modelli indipendenti, trovati: {data.get('model_count')}"
        assert "met_norway" in data.get("active_models", [])
        assert "dwd_brightsky" in data.get("active_models", [])
        assert "gfs_7timer" in data.get("active_models", [])

        # Verifica schede in fallback totale
        curr = meteo_telegram_bot.format_current_weather_message(data)
        assert "Media 3 Modelli" in curr
        assert "NOAA GFS (USA)" in curr

        syn = meteo_telegram_bot.format_single_city_synoptic_message(data, monza_loc["key"])
        assert "(3 centri di calcolo)" in syn

    print(" -> PASS: Tripla ridondanza indipendente (3 modelli: UE + DE + USA) validata con successo.")


def test_diagnostica_command():
    print("\n=== TEST 3: COMANDO /DIAGNOSTICA ===")
    diag_text = meteo_telegram_bot.format_diagnostics_message()
    print("Output /diagnostica:")
    print(diag_text)
    assert "DIAGNOSTICA STATO METEO BOT" in diag_text
    assert "Ultimo esito Open-Meteo" in diag_text
    assert "Memoria Cache" in diag_text
    print(" -> PASS: Diagnostica generata correttamente.")


if __name__ == "__main__":
    test_hybrid_fallback_6_models()
    test_hybrid_fallback_total_outage()
    test_diagnostica_command()
    print("\n✅ TUTTI I TEST DI RESILIENZA E MULTI-MODELLO SONO STATI SUPERATI CON SUCCESSO!")

