#!/usr/bin/env python3
"""
Test di verifica del Fallback Ibrido Multi-Modello (MET Norway + DWD Bright Sky).
Simula il rate limit HTTP 429 su Open-Meteo e certifica che il bot:
1. Attiva l'ensemble ibrido di emergenza combinando MET Norway e DWD Bright Sky.
2. Conserva la media multi-modello (2 centri di calcolo europei).
3. Genera correttamente schede live, bollettini CML ed editoriali sinottici senza degradare a modello singolo.
"""

import sys
import os
from unittest.mock import patch
import urllib.error

# Aggiunge la directory corrente al path di Python
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import meteo_telegram_bot

def test_hybrid_fallback_on_429():
    print("=== TEST RESILIENZA FALLBACK IBRIDO (SIMULAZIONE HTTP 429 OPEN-METEO) ===")
    monza_loc = meteo_telegram_bot.DEFAULT_LOCATIONS["monza"]

    # Simula blocco HTTP 429 costante da Open-Meteo
    def mock_urlopen_429(req, *args, **kwargs):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "open-meteo.com" in url:
            raise urllib.error.HTTPError(url, 429, "Too Many Requests", {}, None)
        # Permetti chiamate reali a api.met.no e api.brightsky.dev
        return _orig_urlopen(req, *args, **kwargs)

    _orig_urlopen = urllib.request.urlopen

    with patch("urllib.request.urlopen", side_effect=mock_urlopen_429):
        print("\n[1] Esecuzione fetch con Open-Meteo simulato in HTTP 429...")
        data = meteo_telegram_bot.parse_location_forecast(monza_loc, force_refresh=True)

        # 1. Verifica sorgente e modelli
        print(f" -> Sorgente rilevata: {data.get('source_label')}")
        print(f" -> Modelli attivi: {data.get('active_models')}")
        print(f" -> Numero modelli: {data.get('model_count')}")

        assert data.get("model_count", 0) >= 2, f"Attesi almeno 2 modelli nel fallback, trovati: {data.get('model_count')}"
        assert "met_norway" in data.get("active_models", []), "Manca met_norway nei modelli attivi"
        assert "dwd_brightsky" in data.get("active_models", []), "Manca dwd_brightsky nei modelli attivi"

        # 2. Verifica scheda meteo in tempo reale (Adesso)
        current_msg = meteo_telegram_bot.format_current_weather_message(data)
        print("\n[2] Output Scheda 'Attuale' in Fallback Ibrido:")
        print(current_msg)
        assert "Media 2 Modelli" in current_msg, "Manca 'Media 2 Modelli' nella scheda attuale"
        assert "MET Norway (UE)" in current_msg, "Manca 'MET Norway (UE)' nei modelli della scheda attuale"
        assert "DWD ICON (DE)" in current_msg, "Manca 'DWD ICON (DE)' nei modelli della scheda attuale"

        # 3. Verifica bollettino CML 3gg
        bulletin_msg = meteo_telegram_bot.format_city_weather_message(data)
        print("\n[3] Output 'Previsioni 3gg' in Fallback Ibrido:")
        print(bulletin_msg)
        assert "media 2 modelli" in bulletin_msg, "Manca 'media 2 modelli' nel bollettino 3gg"
        assert "modello singolo" not in bulletin_msg, "Trovata dicitura indesiderata 'modello singolo'"

        # 4. Verifica editoriale sinottico
        synoptic_msg = meteo_telegram_bot.format_single_city_synoptic_message(data, monza_loc["key"])
        print("\n[4] Output 'Sinottico' in Fallback Ibrido:")
        print(synoptic_msg)
        assert "media multi-modello (2 centri di calcolo)" in synoptic_msg, "Manca 'media multi-modello (2 centri di calcolo)' nel sinottico"
        assert "(1 centri di calcolo)" not in synoptic_msg, "Rilevato bug grammaticale (1 centri di calcolo)"

    print("\n✅ TEST FALLBACK IBRIDO COMPLETATO CON SUCCESSO! La media multi-modello è garantita anche con Open-Meteo in 429.")

if __name__ == "__main__":
    test_hybrid_fallback_on_429()
