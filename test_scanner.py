
import os
import json
from datetime import datetime, timezone
from pathlib import Path

import requests


# ==========================================
# POKEWATCH OPPORTUNITY SCANNER V1.5
# Batch-scanning af Pokemon-saet
# ==========================================

API_KEY = os.environ.get("TCG_API_KEY")

if not API_KEY:
    raise RuntimeError("TCG_API_KEY mangler.")

BASE_URL = "https://api.tcgapi.dev/v1"
HEADERS = {"X-API-Key": API_KEY}

BATCH_SIZE = 10
PER_PAGE = 100
MAX_API_CALLS = 50

MIN_PRICE = 5.0
MAX_PRICE = 200.0

STATE_FILE = Path("scanner_state.json")
OUTPUT_FILE = Path("scanner_candidates.json")

session = requests.Session()
session.headers.update(HEADERS)

api_calls = 0


def fetch(endpoint, params=None):
    global api_calls

    if api_calls >= MAX_API_CALLS:
        raise RuntimeError("API-kaldsgrænsen er nået.")

    api_calls += 1

    response = session.get(
        BASE_URL + endpoint,
        params=params,
        timeout=30,
    )

    response.raise_for_status()
    return response.json()


def load_state():
    if STATE_FILE.exists():
        with STATE_FILE.open(
            "r", encoding="utf-8"
        ) as file:
            return json.load(file)

    return {
        "next_set_index": 0,
        "candidates": {},
    }


def save_state(state):
    with STATE_FILE.open(
        "w", encoding="utf-8"
    ) as file:
        json.dump(
            state,
            file,
            indent=2,
            ensure_ascii=False,
        )


def is_raw_card(card):
    if card.get("product_type") != "Cards":
        return False

    name = str(card.get("name") or "").lower()

    excluded = [
        "battle deck",
        "theme deck",
        "starter deck",
        "tech sticker",
        "sticker collection",
        "booster",
        "blister",
        "collection box",
        "premium collection",
        "trainer box",
        "tin",
        "bundle",
        "case",
        "display",
    ]

    return not any(word in name for word in excluded)


def get_market_price(card):
    value = card.get("market_price")

    if value is None:
        return None

    try:
        price = float(value)
    except (TypeError, ValueError):
        return None

    if MIN_PRICE <= price <= MAX_PRICE:
        return price

    return None


def scan_set(pokemon_set):
    set_id = pokemon_set["id"]
    set_name = pokemon_set.get("name", "Ukendt")

    print("Scanner saet:", set_name)

    found = {}
    page = 1

    while True:
        result = fetch(
            f"/sets/{set_id}/cards",
            {
                "page": page,
                "per_page": PER_PAGE,
            },
        )

        cards = result.get("data", [])
        meta = result.get("meta", {})

        if not isinstance(cards, list):
            raise ValueError("Ugyldigt kortsvar fra API.")

        for card in cards:
            if not isinstance(card, dict):
                continue

            if not is_raw_card(card):
                continue

            price = get_market_price(card)

            if price is None:
                continue

            card_id = card.get("id")

            if card_id is None:
                continue

            printing = card.get("printing") or "Unknown"
            key = f"{card_id}:{printing}"

            found[key] = {
                "card_id": card_id,
                "name": card.get("name"),
                "set_id": set_id,
                "set_name": set_name,
                "number": card.get("number"),
                "rarity": card.get("rarity"),
                "printing": printing,
                "market_price_usd": price,
                "market_price_as_of": card.get(
                    "market_price_as_of"
                ),
                "total_listings": card.get(
                    "total_listings"
                ),
            }

        print(
            "  Side:", page,
            "| Produkter:", len(cards),
            "| Kandidater:", len(found),
        )

        if meta.get("has_more") is False:
            break

        if not cards:
            break

        if (
            len(cards) < PER_PAGE
            and meta.get("has_more") is not True
        ):
            break

        page += 1

    return found


def main():
    print("===================================")
    print("POKEWATCH OPPORTUNITY SCANNER V1.5")
    print("===================================")

    state = load_state()

    result = fetch(
        "/sets",
        {
            "game": "pokemon",
            "page": 1,
            "per_page": 100,
        },
    )

    all_sets = result.get("data", [])
    meta = result.get("meta", {})

    # Hent alle saetsider
    page = 2

    while meta.get("has_more") is True:
        result = fetch(
            "/sets",
            {
                "game": "pokemon",
                "page": page,
                "per_page": 100,
            },
        )

        all_sets.extend(result.get("data", []))
        meta = result.get("meta", {})
        page += 1

    total_sets = len(all_sets)

    print("Pokemon-saet fundet:", total_sets)

    start = state.get("next_set_index", 0)

    if start >= total_sets:
        start = 0
        print("Alle saet gennemgaaet. Starter forfra.")

    end = min(start + BATCH_SIZE, total_sets)

    print("Scanner saet:", start + 1, "til", end)

    completed = 0

    for index in range(start, end):
        pokemon_set = all_sets[index]

        # Efterlad plads til en komplet saetscanning.
        if api_calls >= MAX_API_CALLS - 10:
            print("Stopper for at beskytte API-kvoten.")
            break

        found = scan_set(pokemon_set)

        state["candidates"].update(found)
        state["next_set_index"] = index + 1

        completed += 1

        save_state(state)

    candidates = list(
        state["candidates"].values()
    )

    candidates.sort(
        key=lambda item: (
            -item["market_price_usd"],
            str(item["card_id"]),
        )
    )

    report = {
        "scanner": "PokeWatch Opportunity Scanner",
        "version": "1.5",
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "currency": "USD",
        "next_set_index": state["next_set_index"],
        "total_sets": total_sets,
        "sets_completed_this_run": completed,
        "api_calls": api_calls,
        "total_candidates": len(candidates),
        "candidates": candidates,
    }

    with OUTPUT_FILE.open(
        "w", encoding="utf-8"
    ) as file:
        json.dump(
            report,
            file,
            indent=2,
            ensure_ascii=False,
        )

    print()
    print("===================================")
    print("RESULTAT")
    print("===================================")
    print("Saet gennemgaaet i dag:", completed)
    print("Naeste saet-indeks:", state["next_set_index"])
    print("Samlede kandidater:", len(candidates))
    print("API-kald:", api_calls)
    print("Fremdrift gemt:", STATE_FILE)
    print("Rapport gemt:", OUTPUT_FILE)
    print("TEST AFSLUTTET")


if __name__ == "__main__":
    main()
