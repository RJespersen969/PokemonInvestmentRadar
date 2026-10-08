
import os
import requests

API_KEY = os.environ.get("TCG_API_KEY")

if not API_KEY:
    raise RuntimeError("TCG_API_KEY mangler.")

url = "https://api.tcgapi.dev/v1/search"

params = {
    "q": "eevee",
    "game": "pokemon",
    "type": "Cards",
    "min_price": 5,
    "max_price": 200,
    "per_page": 20,
    "page": 1,
}

response = requests.get(
    url,
    headers={"X-API-Key": API_KEY},
    params=params,
    timeout=30,
)

response.raise_for_status()

result = response.json()
cards = result.get("data", [])
meta = result.get("meta", {})

print("=== POKEWATCH POKEMON SEARCH ===")
print("HTTP-status:", response.status_code)
print("Samlet antal match:", meta.get("total"))
print("Resultater på denne side:", len(cards))
print("Flere sider:", meta.get("has_more"))
print("===============================")

for card in cards:
    if card.get("game_slug") != "pokemon":
        continue

    if card.get("product_type") != "Cards":
        continue

    print(
        f"{card.get('name')} | "
        f"{card.get('set_name')} | "
        f"{card.get('printing')} | "
        f"{card.get('market_price')} USD"
    )

print("===============================")
print("Pokemon-søgning afsluttet.")
