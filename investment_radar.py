
import os
import json
import time
from pathlib import Path
from datetime import datetime, timezone

import requests

API_KEY = os.environ.get("TCG_API_KEY")
BASE_URL = "https://api.tcgapi.dev/v1"

def main():
    if not API_KEY:
        raise RuntimeError("TCG_API_KEY mangler.")

    with open("watchlist.json", encoding="utf-8") as file:
        watchlist = json.load(file)

    results = []
    errors = []

    for product in watchlist["products"]:
        card_id = product["card_id"]
        wanted_printing = product["printing"]

        url = f"{BASE_URL}/cards/{card_id}/prices"

        try:
            response = requests.get(
                url,
                headers={"X-API-Key": API_KEY},
                timeout=30,
            )
            response.raise_for_status()

            prices = response.json().get("data", [])

            if isinstance(prices, dict):
                prices = [prices]

            matching = next(
                (
                    price for price in prices
                    if price.get("printing", "").lower()
                    == wanted_printing.lower()
                ),
                None,
            )

            if matching is None:
                raise ValueError(
                    f"Variant ikke fundet: {wanted_printing}"
                )

            result = {
                "card_id": card_id,
                "tcgplayer_id": product["tcgplayer_id"],
                "name": product["name"],
                "set": product["set"],
                "printing": wanted_printing,
                "category": product["category"],
                "market_price_usd": matching.get("market_price"),
                "price_date": matching.get("market_price_as_of"),
                "price_change_7d": matching.get("price_change_7d"),
            }

            results.append(result)

            print(
                f"{product['name']} | "
                f"{wanted_printing} | "
                f"{result['market_price_usd']} USD"
            )

        except (requests.RequestException, ValueError, KeyError) as error:
            errors.append({
                "card_id": card_id,
                "error": str(error),
            })
            print(f"FEJL ved kort {card_id}: {error}")

        time.sleep(1)

    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "source": "TCG API",
        "currency": "USD",
        "products": results,
        "errors": errors,
    }

    Path("reports").mkdir(exist_ok=True)

    with open("reports/latest.json", "w", encoding="utf-8") as file:
        json.dump(report, file, ensure_ascii=False, indent=2)

    print("--------------------------")
    print("Kort hentet:", len(results))
    print("Fejl:", len(errors))
    print("Rapport gemt: reports/latest.json")

    if errors:
        raise RuntimeError(
            f"{len(errors)} produkter kunne ikke hentes."
        )

if __name__ == "__main__":
    main()
