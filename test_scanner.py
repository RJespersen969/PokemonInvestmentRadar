
import os
from collections import Counter

import requests


# ============================================
# POKEWATCH OPPORTUNITY SCANNER V1.3
# Pokemon-katalog og RAW-prisdiagnose
# ============================================

API_KEY = os.environ.get("TCG_API_KEY")

if not API_KEY:
    raise RuntimeError("TCG_API_KEY mangler.")

BASE_URL = "https://api.tcgapi.dev/v1"
HEADERS = {"X-API-Key": API_KEY}

MIN_PRICE = 5
MAX_PRICE = 200
MAX_SETS = 5


def fetch(endpoint, params=None):
    response = requests.get(
        BASE_URL + endpoint,
        headers=HEADERS,
        params=params,
        timeout=30,
    )

    response.raise_for_status()
    return response.json()


def main():
    print("================================")
    print("POKEWATCH OPPORTUNITY SCANNER")
    print("VERSION 1.3")
    print("================================")

    # Hent Pokemon-saet
    result = fetch(
        "/sets",
        {
            "game": "pokemon",
            "page": 1,
            "per_page": MAX_SETS,
        },
    )

    sets = result.get("data", [])
    metadata = result.get("meta", {})

    print("Pokemon-saet i alt:", metadata.get("total"))
    print("Saet hentet:", len(sets))

    all_cards = []
    product_types = Counter()

    # Undersoeg de foerste fem saet
    for pokemon_set in sets:
        set_id = pokemon_set.get("id")
        set_name = pokemon_set.get("name", "Ukendt")

        if not set_id:
            continue

        print()
        print("================================")
        print("SAET:", set_name)
        print("================================")

        result = fetch(
            f"/sets/{set_id}/cards",
            {
                "page": 1,
                "per_page": 100,
            },
        )

        cards = result.get("data", [])
        metadata = result.get("meta", {})

        print("Produkter i alt:", metadata.get("total"))
        print("Produkter hentet:", len(cards))
        print("Flere sider:", metadata.get("has_more"))

        for card in cards:
            if not isinstance(card, dict):
                continue

            product_type = card.get(
                "product_type", "Ukendt"
            )

            product_types[product_type] += 1

            if product_type != "Cards":
                continue

            price = card.get("market_price")

            if price is None:
                continue

            try:
                price = float(price)
            except (TypeError, ValueError):
                continue

            if MIN_PRICE <= price <= MAX_PRICE:
                all_cards.append({
                    "id": card.get("id"),
                    "name": card.get("name"),
                    "set": set_name,
                    "printing": card.get("printing"),
                    "price": price,
                })

    # Vis fordelingen af produkttyper
    print()
    print("================================")
    print("PRODUKTTYPER")
    print("================================")

    for product_type, count in product_types.items():
        print(product_type, ":", count)

    # Fjern dubletter efter kort-ID og variant
    unique_cards = {}

    for card in all_cards:
        key = (
            card["id"],
            card["printing"],
        )

        unique_cards[key] = card

    candidates = list(unique_cards.values())

    candidates.sort(
        key=lambda card: card["price"],
        reverse=True,
    )

    print()
    print("================================")
    print("RAW-KANDIDATER")
    print("================================")

    print("Antal kandidater:", len(candidates))

    for index, card in enumerate(candidates[:20], 1):
        print()
        print("Nr:", index)
        print("Navn:", card["name"])
        print("Saet:", card["set"])
        print("Variant:", card["printing"])
        print("Pris USD:", card["price"])

    print()
    print("================================")
    print("TEST AFSLUTTET")
    print("================================")


if __name__ == "__main__":
    main()
