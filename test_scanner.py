
import os
import json
import re
from datetime import datetime, timezone

import requests


# ============================================
# POKEWATCH OPPORTUNITY SCANNER V1.4
# RAW Pokemon Card Discovery
# ============================================

API_KEY = os.environ.get("TCG_API_KEY")

if not API_KEY:
    raise RuntimeError("TCG_API_KEY mangler.")

BASE_URL = "https://api.tcgapi.dev/v1"
HEADERS = {"X-API-Key": API_KEY}

MAX_SETS = 5
PER_PAGE = 100
MAX_PAGES_PER_SET = 5

MIN_PRICE = 5.0
MAX_PRICE = 200.0

OUTPUT_FILE = "scanner_candidates.json"

session = requests.Session()
session.headers.update(HEADERS)

api_calls = 0


def fetch(endpoint, params=None):
    global api_calls

    response = session.get(
        BASE_URL + endpoint,
        params=params,
        timeout=30,
    )

    api_calls += 1
    response.raise_for_status()

    return response.json()


def is_raw_card(card):
    if card.get("product_type") != "Cards":
        return False

    name = str(card.get("name") or "").lower()

    # Udeluk kendte ikke-enkeltkort
    excluded_words = [
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

    if any(word in name for word in excluded_words):
        return False

    # Dette er et foreloebigt RAW-filter.
    # Produktnavne alene kan ikke bevise,
    # at varen er et enkeltkort.
    return True


def get_price(card):
    value = card.get("market_price")

    if value is None:
        return None

    try:
        price = float(value)
    except (TypeError, ValueError):
        return None

    if not MIN_PRICE <= price <= MAX_PRICE:
        return None

    return price


def get_set_cards(set_id):
    all_cards = []
    expected_total = None

    for page in range(1, MAX_PAGES_PER_SET + 1):
        result = fetch(
            f"/sets/{set_id}/cards",
            {
                "page": page,
                "per_page": PER_PAGE,
            },
        )

        cards = result.get("data", [])
        metadata = result.get("meta", {})

        if not isinstance(cards, list):
            raise ValueError("Ugyldigt kortsvar fra API.")

        if expected_total is None:
            expected_total = metadata.get("total")

        all_cards.extend(cards)

        print(
            f"  Side {page}: "
            f"{len(cards)} produkter hentet"
        )

        has_more = metadata.get("has_more")

        if has_more is False:
            break

        if not cards:
            break

        if len(cards) < PER_PAGE and has_more is not True:
            break

    return all_cards, expected_total


def main():
    print("====================================")
    print("POKEWATCH OPPORTUNITY SCANNER V1.4")
    print("====================================")

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

    if not isinstance(sets, list):
        raise ValueError("Ugyldigt saetsvar fra API.")

    print("Pokemon-saet i alt:", metadata.get("total"))
    print("Saet i denne scanning:", len(sets))

    candidates = {}
    total_products = 0
    raw_products = 0
    excluded_products = 0
    incomplete_sets = []

    for pokemon_set in sets:
        set_id = pokemon_set.get("id")
        set_name = pokemon_set.get("name", "Ukendt")

        if set_id is None:
            continue

        print()
        print("SAET:", set_name)

        cards, expected_total = get_set_cards(set_id)

        total_products += len(cards)

        if (
            isinstance(expected_total, int)
            and len(cards) < expected_total
        ):
            incomplete_sets.append(set_name)

        for card in cards:
            if not isinstance(card, dict):
                continue

            if not is_raw_card(card):
                excluded_products += 1
                continue

            raw_products += 1

            price = get_price(card)

            if price is None:
                continue

            card_id = card.get("id")
            printing = card.get("printing") or "Unknown"

            if card_id is None:
                continue

            # Samme kort og variant maa ikke taelles
            # flere gange.
            key = f"{card_id}:{printing}"

            candidates[key] = {
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
                "price_updated_at": card.get(
                    "price_updated_at"
                ),
                "total_listings": card.get(
                    "total_listings"
                ),
            }

        print("Produkter gennemgaaet:", len(cards))
        print("Kandidater indtil nu:", len(candidates))

    # Sorter kun efter pris for at faa
    # en reproducerbar oversigt.
    # Det er IKKE en investeringsrangering.
    sorted_candidates = sorted(
        candidates.values(),
        key=lambda item: (
            -item["market_price_usd"],
            str(item["card_id"]),
        ),
    )

    report = {
        "scanner": "PokeWatch Opportunity Scanner",
        "version": "1.4",
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "category": "raw",
        "currency": "USD",
        "filters": {
            "min_price": MIN_PRICE,
            "max_price": MAX_PRICE,
        },
        "coverage": {
            "sets_scanned": len(sets),
            "products_scanned": total_products,
            "possible_raw_products": raw_products,
            "excluded_products": excluded_products,
            "incomplete_sets": incomplete_sets,
            "api_calls": api_calls,
        },
        "candidates": sorted_candidates,
    }

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            report,
            file,
            indent=2,
            ensure_ascii=False,
        )

    print()
    print("====================================")
    print("RESULTAT")
    print("====================================")
    print("Saet scannet:", len(sets))
    print("Produkter scannet:", total_products)
    print("Mulige RAW-produkter:", raw_products)
    print("Udelukkede produkter:", excluded_products)
    print("Kandidater:", len(sorted_candidates))
    print("API-kald:", api_calls)
    print("Ufuldstaendige saet:", incomplete_sets)

    print()
    print("TOP 10 EFTER MARKEDSPRIS")
    print("(Ikke investeringsrangering)")

    for index, card in enumerate(
        sorted_candidates[:10], 1
    ):
        print(
            f"{index}. {card['name']} | "
            f"{card['set_name']} | "
            f"{card['printing']} | "
            f"${card['market_price_usd']:.2f}"
        )

    print()
    print("JSON-fil oprettet:", OUTPUT_FILE)
    print("TEST AFSLUTTET")


if __name__ == "__main__":
    main()
