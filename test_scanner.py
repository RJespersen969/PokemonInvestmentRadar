
import os
import requests

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
        timeout=30
    )
    response.raise_for_status()
    return response.json()


print("=== POKEWATCH V1.3 ===")

# Find Pokemon-saet
result = fetch(
    "/sets",
    {
        "game": "pokemon",
        "page": 1,
        "per_page": 5
    }
)

sets = result.get("data", [])
meta = result.get("meta", {})

print("Pokemon-saet i alt:", meta.get("total"))
print("Saet hentet:", len(sets))

for item in sets:
    print("Saet:", item.get("name"), "| ID:", item.get("id"))

# Test kortene i det foerste saet
if sets:
    first_set = sets[0]
    set_id = first_set["id"]

    result = fetch(
        f"/sets/{set_id}/cards",
        {
            "page": 1,
            "per_page": 100
        }
    )

    cards = result.get("data", [])
    meta = result.get("meta", {})

    print("=== KORT I FOERSTE SAET ===")
    print("Saet:", first_set.get("name"))
    print("Kort i alt:", meta.get("total"))
    print("Kort hentet:", len(cards))
    print("Flere sider:", meta.get("has_more"))

    candidates = []

    for card in cards:
        if card.get("product_type") != "Cards":
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

    print("Kort inden for prisrammen:", len(candidates))

    for card in candidates[:10]:
        print(
            card.get("name"),
            "|", card.get("printing"),
            "|", card.get("market_price"), "USD"
        )

print("=== TEST AFSLUTTET ===")
