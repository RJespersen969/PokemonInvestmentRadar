
import os
import json
import time
import math
from pathlib import Path
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import requests


# ============================================
# POKEWATCH OPPORTUNITY SCANNER V1.6
# Safe batch scanning with rate-limit handling
# ============================================

API_KEY = os.environ.get("TCG_API_KEY")

if not API_KEY:
    raise RuntimeError("TCG_API_KEY mangler.")

BASE_URL = "https://api.tcgapi.dev/v1"

BATCH_SIZE = 5
PER_PAGE = 100
MAX_API_CALLS = 35

REQUEST_DELAY = 2
MAX_RETRY_WAIT = 60

MIN_PRICE = 5.0
MAX_PRICE = 200.0

STATE_FILE = Path("scanner_state.json")
OUTPUT_FILE = Path("scanner_candidates.json")

session = requests.Session()
session.headers.update({
    "X-API-Key": API_KEY
})

api_calls = 0


class RateLimitReached(Exception):
    pass


class ApiBudgetReached(Exception):
    pass


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def retry_after_seconds(value):
    if not value:
        return None

    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        pass

    try:
        retry_time = parsedate_to_datetime(value)

        if retry_time.tzinfo is None:
            retry_time = retry_time.replace(
                tzinfo=timezone.utc
            )

        seconds = (
            retry_time -
            datetime.now(timezone.utc)
        ).total_seconds()

        return max(0, math.ceil(seconds))

    except (TypeError, ValueError, OverflowError):
        return None


def fetch(endpoint, params=None):
    global api_calls

    for attempt in range(2):
        if api_calls >= MAX_API_CALLS:
            raise ApiBudgetReached(
                "API-budget for denne koersel er brugt."
            )

        if api_calls > 0:
            time.sleep(REQUEST_DELAY)

        response = session.get(
            BASE_URL + endpoint,
            params=params,
            timeout=30,
        )

        api_calls += 1

        if response.status_code == 429:
            wait = retry_after_seconds(
                response.headers.get("Retry-After")
            )

            if (
                attempt == 0
                and wait is not None
                and wait <= MAX_RETRY_WAIT
            ):
                print(
                    "HTTP 429. Venter",
                    wait,
                    "sekunder efter API-anvisning."
                )

                time.sleep(wait)
                continue

            raise RateLimitReached(
                "API-kvoten er opbrugt. "
                "Stopper uden flere forsoeg."
            )

        response.raise_for_status()

        return response.json()

    raise RateLimitReached(
        "API afviser fortsat forespoergsler."
    )


def load_state():
    if not STATE_FILE.exists():
        return {
            "next_set_index": 0,
            "candidates": {},
        }

    with STATE_FILE.open(
        "r",
        encoding="utf-8"
    ) as file:
        state = json.load(file)

    if not isinstance(state, dict):
        raise ValueError("Ugyldig scanner_state.json")

    if not isinstance(
        state.get("candidates"), dict
    ):
        raise ValueError("Ugyldigt kandidatformat.")

    return state


def save_json(path, data):
    temporary = path.with_suffix(
        path.suffix + ".tmp"
    )

    with temporary.open(
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            data,
            file,
            indent=2,
            ensure_ascii=False,
        )

    temporary.replace(path)


def is_possible_raw_card(card):
    if card.get("product_type") != "Cards":
        return False

    name = str(
        card.get("name") or ""
    ).lower()

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

    return not any(
        word in name
        for word in excluded
    )


def get_price(card):
    try:
        price = float(
            card.get("market_price")
        )
    except (TypeError, ValueError):
        return None

    if not math.isfinite(price):
        return None

    if MIN_PRICE <= price <= MAX_PRICE:
        return price

    return None


def get_all_sets():
    all_sets = []
    page = 1

    while True:
        result = fetch(
            "/sets",
            {
                "game": "pokemon",
                "page": page,
                "per_page": PER_PAGE,
            },
        )

        data = result.get("data", [])
        meta = result.get("meta", {})

        if not isinstance(data, list):
            raise ValueError(
                "API returnerede ugyldige saet."
            )

        all_sets.extend(data)

        if meta.get("has_more") is False:
            break

        if not data:
            break

        if (
            len(data) < PER_PAGE
            and meta.get("has_more") is not True
        ):
            break

        page += 1

    return all_sets


def scan_set(pokemon_set):
    set_id = pokemon_set["id"]
    set_name = pokemon_set.get(
        "name", "Ukendt"
    )

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
            raise ValueError(
                "API returnerede ugyldige kort."
            )

        print(
            "  Side:", page,
            "| Produkter:", len(cards)
        )

        for card in cards:
            if not isinstance(card, dict):
                continue

            if not is_possible_raw_card(card):
                continue

            price = get_price(card)

            if price is None:
                continue

            card_id = card.get("id")

            if card_id is None:
                continue

            printing = (
                card.get("printing")
                or "Unknown"
            )

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

    print(
        "  Mulige RAW-kandidater:",
        len(found)
    )

    return found


def save_report(state, total_sets, completed, status):
    candidates = sorted(
        state["candidates"].values(),
        key=lambda item: (
            -item["market_price_usd"],
            str(item["card_id"]),
        ),
    )

    report = {
        "scanner": "PokeWatch Opportunity Scanner",
        "version": "1.6",
        "generated_at": utc_now(),
        "status": status,
        "currency": "USD",
        "next_set_index": state["next_set_index"],
        "total_sets": total_sets,
        "sets_completed_this_run": completed,
        "api_calls": api_calls,
        "total_candidates": len(candidates),
        "candidates": candidates,
    }

    save_json(STATE_FILE, state)
    save_json(OUTPUT_FILE, report)

    print()
    print("================================")
    print("RESULTAT")
    print("================================")
    print("Status:", status)
    print("Saet faerdige i denne koersel:", completed)
    print("Naeste saet:", state["next_set_index"] + 1)
    print("Samlede kandidater:", len(candidates))
    print("API-kald:", api_calls)
    print("Filer gemt.")


def main():
    print("================================")
    print("POKEWATCH OPPORTUNITY SCANNER V1.6")
    print("================================")

    state = load_state()
    total_sets = None
    completed = 0
    status = "completed"

    try:
        all_sets = get_all_sets()
        total_sets = len(all_sets)

        print(
            "Pokemon-saet fundet:",
            total_sets
        )

        if total_sets == 0:
            raise ValueError(
                "Ingen Pokemon-saet fundet."
            )

        start = state.get(
            "next_set_index", 0
        )

        if start >= total_sets:
            start = 0

        end = min(
            start + BATCH_SIZE,
            total_sets
        )

        print(
            "Scanner saet",
            start + 1,
            "til",
            end
        )

        for index in range(start, end):
            if api_calls >= MAX_API_CALLS - 10:
                status = "api_budget_stop"
                break

            pokemon_set = all_sets[index]

            print()
            print(
                "SAET:",
                pokemon_set.get("name")
            )

            # Et saet gemmes kun som faerdigt,
            # hvis alle sider er hentet.
            found = scan_set(pokemon_set)

            state["candidates"].update(found)
            state["next_set_index"] = index + 1

            completed += 1

            save_json(STATE_FILE, state)

    except RateLimitReached as error:
        status = "rate_limited"
        print("API-BEGRAENSNING:", error)

    except ApiBudgetReached as error:
        status = "api_budget_stop"
        print("API-BUDGET:", error)

    save_report(
        state,
        total_sets,
        completed,
        status,
    )

    print("TEST AFSLUTTET")


if __name__ == "__main__":
    main()
