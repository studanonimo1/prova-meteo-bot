#!/usr/bin/env python3
"""
Test e validazione del bollettino 3 giorni in stile CML (Centro Meteo Lombardo).
Verifica che l'output sia formattato senza emoji, con analisi sinottica,
orari di pioggia e temperature min/max chiare per Putignano e Monza.
"""

import sys
import os

# Aggiunge la directory corrente al path di Python
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import meteo_telegram_bot

def run_test():
    print("=== TEST BOLLETTINO METEO STILE CML ===")
    locations_to_test = [
        meteo_telegram_bot.DEFAULT_LOCATIONS["monza"],
        meteo_telegram_bot.DEFAULT_LOCATIONS["putignano"]
    ]

    for loc in locations_to_test:
        print(f"\n------------------------------------------------------------")
        print(f"Test per località: {loc['name']} ({loc['lat']}, {loc['lon']})")
        print(f"------------------------------------------------------------")
        data = meteo_telegram_bot.parse_location_forecast(loc, force_refresh=True)
        bulletin = meteo_telegram_bot.format_city_weather_message(data)
        print(bulletin)
        print(f"------------------------------------------------------------")

        # Test modalità solo pioggia
        rain_bulletin = meteo_telegram_bot.format_city_weather_message(data, only_rain=True)
        assert "Analisi sinottica:" in rain_bulletin, "Manca la sezione 'Analisi sinottica:' in rain_bulletin"
        assert "➡" in rain_bulletin, "Manca il marcatore '➡' in rain_bulletin"

        # Verifiche di conformità
        assert "Analisi sinottica:" in bulletin, "Manca la sezione 'Analisi sinottica:'"
        assert "➡" in bulletin, "Manca il marcatore '➡'"
        assert "Tempo previsto:" in bulletin, "Manca 'Tempo previsto:'"
        assert "Temperature:" in bulletin, "Manca 'Temperature:'"
        assert "Venti:" in bulletin, "Manca 'Venti:'"
        
        # Verifica assenza di emoji superflue
        forbidden_emojis = ["☀️", "🌧️", "🌤️", "⛅", "☁️", "💨", "💧", "🌡️", "🔬", "📍", "📅"]
        for emo in forbidden_emojis:
            assert emo not in bulletin, f"Rilevata emoji non consentita: {emo}"
        # Test Editoriale Sinottico Specialistico (Stile Twitter/X)
        synoptic_msg = meteo_telegram_bot.format_single_city_synoptic_message(data, loc["key"])
        print(f"\n--- EDITORIALE SINOTTICO DISCORSO PER {loc['name']} ---")
        print(synoptic_msg)
        print(f"------------------------------------------------------------")

        word_count = len(synoptic_msg.split())
        print(f"[i] Conteggio parole editoriale per {loc['name']}: {word_count} parole.")
        assert word_count >= 180, f"Editoriale troppo breve: {word_count} parole (atteso >= 180)"
        assert "EDITORIALE METEOROLOGICO SPECIALISTICO" in synoptic_msg
        assert "1. ASSETTO BARICO" not in synoptic_msg, "Rilevato vecchio schema a punti elenco 1. ASSETTO BARICO"
        assert "2. DIAGNOSI MASSA D'ARIA" not in synoptic_msg, "Rilevato vecchio schema a punti elenco 2. DIAGNOSI"
        assert loc["name"] in synoptic_msg, f"Nome città {loc['name']} non presente nell'editoriale"

    print("\n✅ TUTTI I TEST SUPERATI CON SUCCESSO! Il bollettino CML e l'editoriale sinottico sono conformi.")

if __name__ == "__main__":
    run_test()
