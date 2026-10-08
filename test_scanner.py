
import os
import json
import requests

API_KEY = os.environ.get("TCG_API_KEY")

if not API_KEY:
    raise RuntimeError("TCG_API_KEY mangler.")

with open("scanner_config.json", encoding="utf-8") as file:
    config = json.load(file)

filters = config["filters"]

response = requests.get(
    "https://api.tcgapi.dev/v1/prices/top-movers",
    headers={"X-API-Key": API_KEY},
    timeout=30,
)
response.raise_for_status()

data = response.json().get("data", [])

if not isinstance(data, list):
    raise ValueError("API returnerede ikke en liste.")


print("=== DIAGNOSE AF API-DATA ===")

for card in data[:5]:
    print("-----------------------")
    print("Navn:", card.get("name"))
    print("Spil:", card.get("game_name"))
    print("Spil-ID:", card.get("game_slug"))
    print("Variant:", card.get("printing"))
    print("Produkttype:", card.get("product_type"))
    print("Pris:", card.get("market_price"))
    print("Prisændring:", card.get("price_change"))
    print("Dato:", card.get("market_price_as_of"))

print("===========================")

print("=== POKEMON PRISDIAGNOSE ===")

pokemon_cards = [
    card for card in data
    if isinstance(card, dict)
    and card.get("game_slug") == "pokemon"
    and card.get("product_type") == "Cards"
]

print("Pokemon-kort i API-svaret:", len(pokemon_cards))

for card in pokemon_cards[:10]:
    print("-----------------------")
    print("Navn:", card.get("name"))
    print("Saet:", card.get("set_name"))
    print("Variant:", card.get("printing"))
    print("Pris USD:", card.get("market_price"))
    print("Price change:", card.get("price_change"))
    print("Pris dato:", card.get("market_price_as_of"))

print("===========================")

candidates = []


for card in data:
    try:
        if not isinstance(card, dict):
            continue

        # Kun Pokémon TCG-kort.
        if card.get("game_slug") != "pokemon":
            continue

        # Udeluk andre produkttyper.
        if card.get("product_type") != "Cards":
            continue


        # Kun fysiske kort med markedspris.
        price = card.get("market_price")
        change = card.get("price_change")

        if price is None or change is None:
            continue

        price = float(price)
        change = float(change)

        if not (
            filters["min_market_price_usd"]
            <= price
            <= filters["max_market_price_usd"]
        ):
            continue

        if not (
            filters["min_price_change_7d_pct"]
            <= change
            <= filters["max_price_change_7d_pct"]
        ):
            continue

        candidates.append({
            "card_id": card.get("card_id"),
            "name": card.get("name"),
            "set": card.get("set_name"),
            "printing": card.get("printing"),
            "market_price_usd": price,
            "reported_price_change": change,
            "price_date": card.get("market_price_as_of"),
        })

    except (ValueError, TypeError):
        continue

# Største absolutte prisbevægelser først.
candidates.sort(
    key=lambda item: abs(item["reported_price_change"]),
    reverse=True,
)

candidates = candidates[:config["max_opportunities"]]

print("================================")
print("POKEWATCH OPPORTUNITY SCANNER")
print("================================")
print("Kort modtaget fra API:", len(data))
print("Kandidater efter filtrering:", len(candidates))

for index, card in enumerate(candidates, 1):
    print(
        f"{index}. {card['name']} | "
        f"{card['set']} | "
        f"{card['market_price_usd']} USD | "
        f"Ændring: {card['reported_price_change']}"
    )

print("================================")
print("Scanner-test afsluttet.")
