
import os
import json
import time
from pathlib import Path
from datetime import datetime, timezone, date, timedelta

import requests

API_KEY = os.environ.get("TCG_API_KEY")
BASE_URL = "https://api.tcgapi.dev/v1"
HISTORY_FILE = Path("price_history.json")


def calculate_change(observations, card_id, printing, current_date, current_price, days):
    """Beregn prisændring mod en observation mindst X dage gammel."""
    target_date = current_date - timedelta(days=days)

    candidates = [
        item for item in observations
        if item.get("card_id") == card_id
        and item.get("printing") == printing
        and date.fromisoformat(item["date"][:10]) <= target_date
        and item.get("market_price_usd") is not None
    ]

    if not candidates:
        return None

    previous = max(candidates, key=lambda item: item["date"])
    previous_price = float(previous["market_price_usd"])

    if previous_price <= 0:
        return None

    return round(
        (float(current_price) - previous_price) / previous_price * 100,
        2,
    )


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

            observation_date = date.fromisoformat(price_date[:10])

            observation = {
                "card_id": card_id,
                "name": product["name"],
                "printing": wanted_printing,
                "date": observation_date.isoformat(),
                "market_price_usd": price,
            }

            # Undgå dubletter fra samme kort, variant og dato.
            observations[:] = [
                old for old in observations
                if not (
                    old.get("card_id") == card_id
                    and old.get("printing") == wanted_printing
                    and old.get("date", "")[:10] == observation["date"]
                )
            ]
            observations.append(observation)

            analysis = {
                "change_30d_pct": calculate_change(
                    observations, card_id, wanted_printing,
                    observation_date, price, 30
                ),
                "change_90d_pct": calculate_change(
                    observations, card_id, wanted_printing,
                    observation_date, price, 90
                ),
                "change_365d_pct": calculate_change(
                    observations, card_id, wanted_printing,
                    observation_date, price, 365
                ),
            }

            results.append({
                **observation,
                "analysis": analysis,
            })

            print(
                f"{product['name']} | {price} USD | "
                f"30d: {analysis['change_30d_pct']}% | "
                f"90d: {analysis['change_90d_pct']}% | "
                f"365d: {analysis['change_365d_pct']}%"
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

    if errors:
        raise RuntimeError(
            f"{len(errors)} produkter kunne ikke hentes."
        )

    with HISTORY_FILE.open("w", encoding="utf-8") as file:
        json.dump(history, file, ensure_ascii=False, indent=2)

    print("--------------------------")
    print("Kort hentet:", len(results))
    print("Observationer i historik:", len(observations))
    print("Prisanalyse gemt i rapporten.")


if __name__ == "__main__":
    main()
