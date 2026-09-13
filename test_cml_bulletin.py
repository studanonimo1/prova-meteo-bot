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

    print("\n✅ TUTTI I TEST SUPERATI CON SUCCESSO! Il bollettino è conforme alle specifiche CML e privo di emoji.")

if __name__ == "__main__":
    run_test()
