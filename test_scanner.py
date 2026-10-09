
# ============================================================
# POKEWATCH OPPORTUNITY SCANNER V1.9.1
# RAW Pokemon cards | Persistent checkpoints | Discord-ready
# ============================================================

import os
import json
import time
import math
from pathlib import Path
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import requests


# ---------------- CONFIGURATION ----------------

API_KEY = os.environ.get("TCG_API_KEY")

if not API_KEY:
    raise RuntimeError("TCG_API_KEY mangler i GitHub Secrets.")

BASE_URL = "https://api.tcgapi.dev/v1"

BATCH_SIZE = 5
PER_PAGE = 100
MAX_API_CALLS = 35
REQUEST_DELAY = 2
MAX_RETRY_WAIT = 60

MIN_PRICE = 5.0
MAX_PRICE = 200.0

STATE_FILE = Path("scanner_state.json")
HISTORY_FILE = Path("scanner_price_history.json")
OUTPUT_FILE = Path("scanner_candidates.json")

session = requests.Session()
session.headers.update({"X-API-Key": API_KEY})

api_calls = 0


# ---------------- EXCEPTIONS ----------------

class RateLimitReached(Exception):
    pass


class ApiBudgetReached(Exception):
    pass


# ---------------- FILE HANDLING ----------------

def now_utc():
    return datetime.now(timezone.utc)


def save_json(path, data):
    temporary = path.with_suffix(path.suffix + ".tmp")

    with temporary.open("w", encoding="utf-8") as file:
        json.dump(
            data,
            file,
            indent=2,
            ensure_ascii=False
        )

    temporary.replace(path)


def load_json(path, default):
    if not path.exists():
        return default

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def load_state():
    state = load_json(
        STATE_FILE,
        {
            "next_set_index": 0,
            "next_page": 1,
            "next_catalogue_page": 1,
            "catalogue_complete": False,
            "cached_sets": [],
            "candidates": {}
        }
    )

    if not isinstance(state, dict):
        raise ValueError("Ugyldig scanner_state.json")

    state.setdefault("next_set_index", 0)
    state.setdefault("next_page", 1)
    state.setdefault("next_catalogue_page", 1)
    state.setdefault("catalogue_complete", False)
    state.setdefault("cached_sets", [])
    state.setdefault("candidates", {})

    for field, minimum in [
        ("next_set_index", 0),
        ("next_page", 1),
        ("next_catalogue_page", 1)
    ]:
        value = state[field]

        if (
            not isinstance(value, int)
            or isinstance(value, bool)
            or value < minimum
        ):
            raise ValueError("Ugyldig state: " + field)

    if not isinstance(state["cached_sets"], list):
        raise ValueError("Ugyldig saet-cache.")

    if not isinstance(state["candidates"], dict):
        raise ValueError("Ugyldige kandidater.")

    return state


def load_history():
    history = load_json(
        HISTORY_FILE,
        {
            "version": "1.9.1",
            "currency": "USD",
            "observations": {}
        }
    )

    if not isinstance(history, dict):
        raise ValueError("Ugyldig prishistorik.")

    if not isinstance(history.get("observations"), dict):
        raise ValueError("Ugyldige prisobservationer.")

    history["version"] = "1.9.1"
    history["currency"] = "USD"

    return history


# ---------------- API HANDLING ----------------

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

        return max(
            0,
            math.ceil(
                (retry_time - now_utc()).total_seconds()
            )
        )

    except (TypeError, ValueError, OverflowError):
        return None


def fetch(endpoint, params=None):
    global api_calls

    for attempt in range(2):

        if api_calls >= MAX_API_CALLS:
            raise ApiBudgetReached(
                "Maksimalt antal API-kald naaet."
            )

        if api_calls > 0:
            time.sleep(REQUEST_DELAY)

        response = session.get(
            BASE_URL + endpoint,
            params=params,
            timeout=30
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
                    "HTTP 429 - venter",
                    wait,
                    "sekunder."
                )

                time.sleep(wait)
                continue

            raise RateLimitReached(
                "HTTP 429: API-kvote opbrugt."
            )

        response.raise_for_status()
        return response.json()

    raise RateLimitReached(
        "API'et afviser fortsat forespoergsler."
    )


# ---------------- POKEMON SET CATALOGUE ----------------

def get_all_sets(state):
    cached = state["cached_sets"]

    if state["catalogue_complete"] and cached:
        print(
            "Bruger gemt katalog:",
            len(cached),
            "Pokemon-saet."
        )
        return cached

    page = state["next_catalogue_page"]

    print(
        "Fortsaetter katalog fra side:",
        page
    )

    while True:
        result = fetch(
            "/sets",
            {
                "game": "pokemon",
                "page": page,
                "per_page": PER_PAGE
            }
        )

        data = result.get("data", [])
        meta = result.get("meta", {})

        if not isinstance(data, list):
            raise ValueError("Ugyldigt katalogsvar.")

        # Undgaa dubletter ved gentagne koersler.
        existing_ids = {
            str(item.get("id"))
            for item in cached
            if isinstance(item, dict)
        }

        for pokemon_set in data:
            if not isinstance(pokemon_set, dict):
                continue

            set_id = pokemon_set.get("id")

            if set_id is None:
                continue

            key = str(set_id)

            if key not in existing_ids:
                cached.append(pokemon_set)
                existing_ids.add(key)

        finished = (
            meta.get("has_more") is False
            or not data
            or (
                len(data) < PER_PAGE
                and meta.get("has_more") is not True
            )
        )

        state["cached_sets"] = cached
        state["next_catalogue_page"] = page + 1
        state["catalogue_complete"] = finished

        # Gem kataloget efter hver side.
        save_json(STATE_FILE, state)

        print(
            "Katalog gemt:",
            len(cached),
            "saet | side",
            page
        )

        if finished:
            print("Pokemon-katalog faerdigt.")
            return cached

        page += 1


# ---------------- CARD FILTERS ----------------

def get_price(card):
    try:
        price = float(card.get("market_price"))
    except (TypeError, ValueError):
        return None

    if not math.isfinite(price) or price <= 0:
        return None

    return round(price, 2)


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
        "display"
    ]

    return not any(
        word in name
        for word in excluded
    )


def card_key(card):
    card_id = card.get("id")

    if card_id is None:
        return None

    printing = card.get("printing") or "Unknown"

    return f"{card_id}:{printing}"


# ---------------- PRICE HISTORY ----------------

def record_price(history, card, set_name, set_id):
    price = get_price(card)
    key = card_key(card)

    if price is None or key is None:
        return False

    observations = history["observations"]

    if key not in observations:
        observations[key] = {
            "card_id": card.get("id"),
            "name": card.get("name"),
            "set_id": set_id,
            "set_name": set_name,
            "printing": card.get("printing") or "Unknown",
            "prices": []
        }

    entry = observations[key]

    if not isinstance(entry.get("prices"), list):
        raise ValueError(
            "Ugyldig prishistorik for " + key
        )

    today = now_utc().date().isoformat()

    observation = {
        "date": today,
        "market_price_usd": price,
        "market_price_as_of": card.get(
            "market_price_as_of"
        )
    }

    for index, existing in enumerate(entry["prices"]):
        if existing.get("date") == today:
            entry["prices"][index] = observation
            return False

    entry["prices"].append(observation)

    entry["prices"].sort(
        key=lambda item: item["date"]
    )

    return True


# ---------------- CARD PROCESSING ----------------

def process_page(cards, pokemon_set, state, history):
    set_id = pokemon_set["id"]
    set_name = pokemon_set.get("name", "Ukendt")

    candidates_found = 0
    new_observations = 0

    for card in cards:
        if not isinstance(card, dict):
            continue

        if not is_raw_card(card):
            continue

        price = get_price(card)
        key = card_key(card)

        if price is None or key is None:
            continue

        if MIN_PRICE <= price <= MAX_PRICE:
            state["candidates"][key] = {
                "card_id": card.get("id"),
                "name": card.get("name"),
                "set_id": set_id,
                "set_name": set_name,
                "number": card.get("number"),
                "rarity": card.get("rarity"),
                "printing": card.get("printing") or "Unknown",
                "market_price_usd": price,
                "market_price_as_of": card.get(
                    "market_price_as_of"
                ),
                "total_listings": card.get(
                    "total_listings"
                )
            }

            candidates_found += 1

        if record_price(
            history,
            card,
            set_name,
            set_id
        ):
            new_observations += 1

    return candidates_found, new_observations


# ---------------- SET SCANNING ----------------

def scan_set(pokemon_set, state, history):
    set_id = pokemon_set["id"]
    set_name = pokemon_set.get("name", "Ukendt")

    page = state["next_page"]

    print()
    print("Scanner saet:", set_name)
    print("Starter paa side:", page)

    while True:
        result = fetch(
            f"/sets/{set_id}/cards",
            {
                "page": page,
                "per_page": PER_PAGE
            }
        )

        cards = result.get("data", [])
        meta = result.get("meta", {})

        if not isinstance(cards, list):
            raise ValueError("Ugyldigt kortsvar.")

        found, observations = process_page(
            cards,
            pokemon_set,
            state,
            history
        )

        finished = (
            meta.get("has_more") is False
            or not cards
            or (
                len(cards) < PER_PAGE
                and meta.get("has_more") is not True
            )
        )

        if finished:
            state["next_set_index"] += 1
            state["next_page"] = 1
        else:
            state["next_page"] = page + 1

        # Gem fremskridt efter hver kortside.
        save_json(HISTORY_FILE, history)
        save_json(STATE_FILE, state)

        print(
            "Side:", page,
            "| RAW-kandidater:", found,
            "| Nye prisobservationer:", observations
        )

        print(
            "Checkpoint:",
            state["next_set_index"],
            state["next_page"]
        )

        if finished:
            return

        page += 1


# ---------------- REPORTING ----------------

def save_report(
    state,
    history,
    total_sets,
    completed,
    status
):
    candidates = sorted(
        state["candidates"].values(),
        key=lambda item: (
            -item["market_price_usd"],
            str(item["card_id"])
        )
    )

    report = {
        "scanner": "PokeWatch Opportunity Scanner",
        "version": "1.9.1",
        "generated_at": now_utc().isoformat(),
        "status": status,
        "currency": "USD",
        "next_set_index": state["next_set_index"],
        "next_page": state["next_page"],
        "next_catalogue_page": state[
            "next_catalogue_page"
        ],
        "catalogue_complete": state[
            "catalogue_complete"
        ],
        "total_sets": total_sets,
        "sets_completed_this_run": completed,
        "api_calls": api_calls,
        "total_candidates": len(candidates),
        "cards_with_price_history": len(
            history["observations"]
        ),
        "candidates": candidates
    }

    save_json(STATE_FILE, state)
    save_json(HISTORY_FILE, history)
    save_json(OUTPUT_FILE, report)

    print()
    print("================================")
    print("POKEWATCH RESULTAT")
    print("================================")
    print("Version: 1.9.1")
    print("Status:", status)
    print("API-kald:", api_calls)
    print("Saet faerdige:", completed)
    print("RAW-kandidater:", len(candidates))
    print(
        "Kort med prishistorik:",
        len(history["observations"])
    )
    print("Alle filer gemt.")


# ---------------- MAIN SCANNER ----------------

def main():
    print("================================")
    print("POKEWATCH OPPORTUNITY SCANNER")
    print("VERSION 1.9.1")
    print("================================")

    state = load_state()
    history = load_history()

    total_sets = None
    completed = 0
    status = "completed"

    try:
        all_sets = get_all_sets(state)
        total_sets = len(all_sets)

        if total_sets == 0:
            raise ValueError(
                "Ingen Pokemon-saet fundet."
            )

        start = state["next_set_index"]

        if start >= total_sets:
            start = 0
            state["next_set_index"] = 0
            state["next_page"] = 1

        target = min(
            start + BATCH_SIZE,
            total_sets
        )

        print(
            "Scanner saet",
            start + 1,
            "til",
            target
        )

        while state["next_set_index"] < target:

            if api_calls >= MAX_API_CALLS - 2:
                status = "api_budget_stop"
                break

            index = state["next_set_index"]
            pokemon_set = all_sets[index]

            scan_set(
                pokemon_set,
                state,
                history
            )

            completed += 1

    except RateLimitReached as error:
        status = "rate_limited"
        print("API-BEGRAENSNING:", error)

    except ApiBudgetReached as error:
        status = "api_budget_stop"
        print("API-BUDGET:", error)

    save_report(
        state,
        history,
        total_sets,
        completed,
        status
    )

    print("SCANNING AFSLUTTET")


if __name__ == "__main__":
    main()
