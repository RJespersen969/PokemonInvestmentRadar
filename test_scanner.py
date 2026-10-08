
import os
import requests

# ==========================================
# POKEWATCH OPPORTUNITY SCANNER V1.3
# Test af Pokemon-saet, kort og prisdata
# ==========================================

API_KEY = os.environ.get("TCG_API_KEY")

if not API_KEY:
    raise RuntimeError("TCG_API_KEY mangler.")

BASE_URL = "https://api.tcgapi.dev/v1"
HEADERS = {"X-API-Key": API_KEY}


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
    print("=== POKEWATCH V1.3 ===")

    # 1. Hent de foerste 5 Pokemon-saet
    result = fetch(
        "/sets",
        {
            "game": "pokemon",
            "page": 1,
            "per_page": 5,
        },
    )

    sets = result.get("data", [])
    meta = result.get("meta", {})

    print("Pokemon-saet i alt:", meta.get("total"))
    print("Saet hentet:", len(sets))

    for item in sets:
        print(
            "Saet:", item.get("name"),
            "| ID:", item.get("id"),
        )

    if not sets:
        print("Ingen Pokemon-saet fundet.")
        return

    # 2. Hent kort fra det foerste saet
    first_set = sets[0]
    set_id = first_set["id"]

    result = fetch(
        f"/sets/{set_id}/cards",
        {
            "page": 1,
            "per_page": 100,
        },
    )

    cards = result.get("data", [])
    meta = result.get("meta", {})

    print("=== KORT I FOERSTE SAET ===")
    print("Saet:", first_set.get("name"))
    print("Kort i alt:", meta.get("total"))
    print("Kort hentet:", len(cards))
    print("Flere sider:", meta.get("has_more"))

    # 3. Undersoeg prisdata og felter
    print("=== PRISDIAGNOSE ===")

    for card in cards[:5]:
        print("-------------------")
        print("Navn:", card.get("name"))
        print("Kort-ID:", card.get("id"))
        print("Produkttype:", card.get("product_type"))
        print("Variant:", card.get("printing"))
        print("Markedspris:", card.get("market_price"))
        print("Tilgaengelige felter:", list(card.keys()))

    print("===================")

    # 4. Find kort i vores prisramme
    candidates = []

    for card in cards:
        if card.get("product_type") not in (None, "Cards"):
            continue

        price = card.get("market_price")

        if price is None:
            continue

        try:
            price = float(price)
        except (TypeError, ValueError):
            continue

        if 5 <= price <= 200:
            candidates.append(card)

print("=== PRODUKTTYPER ===")

types = {}

for card in cards:
    product_type = card.get("product_type", "Ukendt")
    types[product_type] = types.get(product_type, 0) + 1

for product_type, count in types.items():
    print(product_type, ":", count)

print("====================")

    print("=== PRISFILTER ===")
    print("Kort inden for prisrammen:", len(candidates))

    for card in candidates[:10]:
        print(
            card.get("name"),
            "|", card.get("printing"),
            "|", card.get("market_price"), "USD",
        )

    print("=== TEST AFSLUTTET ===")


if __name__ == "__main__":
    main()
