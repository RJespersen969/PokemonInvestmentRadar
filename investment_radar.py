
import os
import requests
from datetime import datetime, timezone

API_KEY = os.environ.get("TCG_API_KEY")
URL = "https://api.tcgapi.dev/v1/prices/top-movers"

def main():
    print("PokéWatch Investment Radar V1")
    print("Dato:", datetime.now(timezone.utc).isoformat())

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

    print("API-status:", response.status_code)
    response.raise_for_status()

    data = response.json()
    cards = data.get("data", [])

    print("Antal resultater:", len(cards))

    for card in cards:
        print("-------------------------")
        print("Navn:", card.get("name"))
        print("Sæt:", card.get("set_name"))
        print("Variant:", card.get("printing"))
        print("Markedspris:", card.get("market_price"))
        print("Prisændring:", card.get("price_change"), "%")

    if not cards:
        print("Ingen resultater modtaget.")

if __name__ == "__main__":
    main()
