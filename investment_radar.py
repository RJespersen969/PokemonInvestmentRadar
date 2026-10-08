
import os
import json
import time
from pathlib import Path
from datetime import datetime, timezone

import requests

API_KEY = os.environ.get("TCG_API_KEY")
BASE_URL = "https://api.tcgapi.dev/v1"
HISTORY_FILE = Path("price_history.json")


def main():
    if not API_KEY:
        raise RuntimeError("TCG_API_KEY mangler.")

    with open("watchlist.json", encoding="utf-8") as file:
        watchlist = json.load(file)

    with HISTORY_FILE.open(encoding="utf-8") as file:
        history = json.load(file)

    observations = history["observations"]
    results = []
    errors = []

    for product in watchlist["products"]:
        card_id = product["card_id"]
        wanted_printing = product["printing"]

        try:
            response = requests.get(
                f"{BASE_URL}/cards/{card_id}/prices",
                headers={"X-API-Key": API_KEY},
                timeout=30,
            )
            response.raise_for_status()

            prices = response.json().get("data", [])
            if isinstance(prices, dict):
                prices = [prices]

            matching = next(
                (
                    p for p in prices
                    if p.get("printing", "").lower()
                    == wanted_printing.lower()
                ),
                None,
            )

            if matching is None:
                raise ValueError("Kortvariant ikke fundet.")

            price = matching.get("market_price")
            price_date = matching.get("market_price_as_of")

            if price is None or not price_date:
                raise ValueError("Pris eller prisdato mangler.")

            observation = {
                "card_id": card_id,
                "name": product["name"],
                "printing": wanted_printing,
                "date": price_date,
                "market_price_usd": price,
            }

            # Opdater eksisterende observation fra samme dato.
            observations[:] = [
                old for old in observations
                if not (
                    old.get("card_id") == card_id
                    and old.get("printing") == wanted_printing
                    and old.get("date") == price_date
                )
            ]
            observations.append(observation)
            results.append(observation)

            print(
                f"{product['name']} | "
                f"{wanted_printing} | "
                f"{price} USD | {price_date}"
            )

        except (requests.RequestException, ValueError, KeyError) as error:
            errors.append({
                "card_id": card_id,
                "error": str(error),
            })
            print(f"FEJL ved kort {card_id}: {error}")

        time.sleep(1)

    observations.sort(
        key=lambda item: (
            item["date"],
            item["card_id"],
            item["printing"],
        )
    )

    history["observations"] = observations

    Path("reports").mkdir(exist_ok=True)

    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "source": "TCG API",
        "currency": "USD",
        "products": results,
        "errors": errors,
    }

    with open("reports/latest.json", "w", encoding="utf-8") as file:
        json.dump(report, file, ensure_ascii=False, indent=2)

    # Gem kun historikken, hvis alle opslag lykkedes.
    if errors:
        raise RuntimeError(
            f"{len(errors)} produkter kunne ikke hentes."
        )

    with HISTORY_FILE.open("w", encoding="utf-8") as file:
        json.dump(history, file, ensure_ascii=False, indent=2)

    print("--------------------------")
    print("Kort hentet:", len(results))
    print("Observationer i historik:", len(observations))
    print("Historik opdateret.")


if __name__ == "__main__":
    main()
