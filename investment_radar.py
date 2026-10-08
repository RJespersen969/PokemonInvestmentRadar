
import os
import json
import requests
from pathlib import Path
from datetime import datetime, timezone

API_KEY = os.environ.get("TCG_API_KEY")
CARD_ID = 35483

def main():
    if not API_KEY:
        raise RuntimeError("TCG_API_KEY mangler.")

    url = f"https://api.tcgapi.dev/v1/cards/{CARD_ID}/prices"

    response = requests.get(
        url,
        headers={"X-API-Key": API_KEY},
        timeout=30
    )

    print("API-status:", response.status_code)
    response.raise_for_status()

    payload = response.json()
    prices = payload.get("data", [])
    if isinstance(prices, dict):
        prices = [prices]

    print("Antal prisvarianter:", len(prices))

    for price in prices:
        print("Variant:", price.get("printing"))
        print("Markedspris:", price.get("market_price"))
        print("Prisdato:", price.get("market_price_as_of"))
        print("7-dages ændring:", price.get("price_change_7d"))
        print("---")

    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "source": "TCG API",
        "card_id": CARD_ID,
        "prices": prices
    }

    Path("reports").mkdir(exist_ok=True)
    with open("reports/latest.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("Rapport gemt.")

if __name__ == "__main__":
    main()
