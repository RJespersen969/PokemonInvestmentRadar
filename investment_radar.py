
import os
import json
import requests
from pathlib import Path
from datetime import datetime, timezone

API_KEY = os.environ.get("TCG_API_KEY")
URL = "https://api.tcgapi.dev/v1/prices/top-movers"

def main():
    if not API_KEY:
        raise RuntimeError("TCG_API_KEY mangler.")

    params = {
        "game": "pokemon",
        "direction": "up",
        "period": "7d",
        "type": "Cards",
        "limit": 5,
    }

    response = requests.get(
        URL,
        headers={"X-API-Key": API_KEY},
        params=params,
        timeout=30,
    )
    response.raise_for_status()

    data = response.json()
    cards = data.get("data", [])

    timestamp = datetime.now(timezone.utc).isoformat()

    report = {
        "timestamp_utc": timestamp,
        "source": "TCG API",
        "query": params,
        "cards": cards,
    }

    Path("reports").mkdir(exist_ok=True)

    with open("reports/latest.json", "w", encoding="utf-8") as file:
        json.dump(report, file, ensure_ascii=False, indent=2)

    print("PokéWatch Investment Radar V1")
    print("API-status:", response.status_code)
    print("Antal resultater:", len(cards))
    print("Rapport gemt: reports/latest.json")

    for card in cards:
        print(
            card.get("name"),
            "| Pris:", card.get("market_price"),
            "| Ændring:", card.get("price_change"), "%"
        )

if __name__ == "__main__":
    main()
