
import json
import os
from pathlib import Path
from datetime import datetime, timezone, date

import requests


# POKEWATCH MARKET ANALYSIS V2.0
# Discord webhook fra GitHub Secrets
WEBHOOK = os.environ.get("DISCORD_MARKET_ANALYSIS_WEBHOOK", "").strip()

CANDIDATES_FILE = Path("scanner_candidates.json")
HISTORY_FILE = Path("scanner_price_history.json")

MAX_CARDS = 10
MIN_PRICE = 5.0
MAX_PRICE = 200.0
MIN_HISTORY_DAYS = 30


def load_json(path):
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def get_price_history(card, history_data):
    observations = history_data.get("observations", {})
    if not isinstance(observations, dict):
        return []

    card_id = str(card.get("card_id", ""))
    printing = str(card.get("printing", ""))
    key = f"{card_id}:{printing}"

    record = observations.get(key, {})
    if not isinstance(record, dict):
        return []

    prices = record.get("prices", [])
    if not isinstance(prices, list):
        return []

    daily = {}

    for entry in prices:
        try:
            day = str(entry["date"])[:10]
            date.fromisoformat(day)
            price = float(entry["market_price_usd"])

            if price > 0:
                daily[day] = price
        except (KeyError, ValueError, TypeError):
            continue

    return sorted(daily.items())


def calculate_score(card, history):
    """
    Score 0-100:
    - Prisfald: 35 point
    - Langsigtet prisudvikling: 30 point
    - Prisstabilitet: 20 point
    - Datakvalitet: 15 point

    Der gives kun score ved mindst 30 dages historik.
    """

    if len(history) < 2:
        return None

    first_day = date.fromisoformat(history[0][0])
    last_day = date.fromisoformat(history[-1][0])

    days = (last_day - first_day).days

    if days < MIN_HISTORY_DAYS:
        return None

    first_price = history[0][1]
    current_price = history[-1][1]

    if first_price <= 0:
        return None

    change_pct = (
        (current_price - first_price) / first_price
    ) * 100

    # 1. Prisfald: maks. 35 point
    # 20% fald eller mere giver fuld score.
    drop_score = min(
        35.0,
        max(0.0, -change_pct / 20.0 * 35.0)
    )

    # 2. Prisudvikling: maks. 30 point
    # Neutral udvikling = 15 point.
    # Stigende pris kan give op til 30 point.
    # Faldende pris reducerer denne del.
    trend_score = max(
        0.0,
        min(30.0, 15.0 + change_pct * 0.75)
    )

    # 3. Prisstabilitet: maks. 20 point
    changes = []

    for index in range(1, len(history)):
        previous = history[index - 1][1]
        current = history[index][1]

        if previous > 0:
            changes.append(
                abs((current - previous) / previous) * 100
            )

    if changes:
        average_movement = sum(changes) / len(changes)
        stability_score = max(
            0.0,
            20.0 - average_movement * 2.0
        )
    else:
        stability_score = 0.0

    # 4. Datakvalitet: maks. 15 point
    # Belønner mange forskellige prisobservationer.
    coverage = min(1.0, len(history) / 30.0)
    data_score = 15.0 * coverage

    total = (
        drop_score
        + trend_score
        + stability_score
        + data_score
    )

    return {
        "score": round(min(100.0, max(0.0, total))),
        "change_pct": round(change_pct, 1),
        "days": days,
        "observations": len(history),
    }


def build_watchlist(cards, history_data):
    results = []

    for card in cards:
        try:
            price = float(card["market_price_usd"])
            listings = int(card.get("total_listings") or 0)

            if not MIN_PRICE <= price <= MAX_PRICE:
                continue

            history = get_price_history(card, history_data)
            analysis = calculate_score(card, history)

            results.append({
                "card": card,
                "price": price,
                "listings": listings,
                "analysis": analysis,
                "history_count": len(history),
            })

        except (KeyError, ValueError, TypeError):
            continue

    # Kort med tilstrækkelig historik kommer først.
    # Derefter højeste score.
    # Kort uden score sorteres efter antal annoncer.
    results.sort(
        key=lambda item: (
            item["analysis"] is None,
            -(
                item["analysis"]["score"]
                if item["analysis"]
                else 0
            ),
            -item["listings"],
        )
    )

    return results[:MAX_CARDS]


def format_card(index, item):
    card = item["card"]

    name = str(card.get("name", "Ukendt kort"))[:100]
    set_name = str(card.get("set_name", "Ukendt saet"))[:80]

    price = item["price"]
    listings = item["listings"]
    analysis = item["analysis"]

    lines = [
        f"**{index}. {name}**",
        f"{set_name}",
        f"RAW pris: **${price:.2f}**",
        f"Annoncer: {listings}",
    ]

    if analysis is None:
        lines.append("Status: Under overvågning")
        lines.append(
            f"Prismålinger: {item['history_count']}"
        )
    else:
        score = analysis["score"]
        change = analysis["change_pct"]

        lines.append(f"Investeringsscore: **{score}/100**")
        lines.append(f"Prisudvikling: **{change:+.1f}%**")
        lines.append(
            f"Historik: {analysis['days']} dage"
        )

        if score >= 75:
            lines.append("Status: Høj prioritet til analyse")
        elif score >= 50:
            lines.append("Status: Interessant at undersøge")
        else:
            lines.append("Status: Fortsat overvågning")

    return "\n".join(lines)


def send_discord(watchlist, report):
    if not WEBHOOK:
        print("Discord webhook mangler - springer over.")
        return

    if not watchlist:
        print("Ingen RAW-kort til markedsanalysen.")
        return

    lines = []

    for index, item in enumerate(watchlist, 1):
        lines.append(format_card(index, item))

    generated = str(
        report.get("generated_at")
        or datetime.now(timezone.utc).isoformat()
    )[:10]

    scored_count = sum(
        item["analysis"] is not None
        for item in watchlist
    )

    payload = {
        "username": "PokeWatch Market Analysis",
        "embeds": [
            {
                "title": "PokéWatch | Market Analysis V2.0",
                "description": "\n\n".join(lines)[:3900],
                "color": 3447003,
                "fields": [
                    {
                        "name": "RAW-kandidater",
                        "value": str(
                            report.get("total_candidates", 0)
                        ),
                        "inline": True,
                    },
                    {
                        "name": "Kort med score",
                        "value": str(scored_count),
                        "inline": True,
                    },
                    {
                        "name": "Dato",
                        "value": generated,
                        "inline": True,
                    },
                ],
                "footer": {
                    "text": (
                        "Eksperimentel score baseret på "
                        "prishistorik. Ikke et automatisk købssignal."
                    )
                },
            }
        ],
    }

    response = requests.post(
        WEBHOOK,
        json=payload,
        timeout=20,
    )

    response.raise_for_status()

    print(
        "PokeWatch Market Analysis V2.0 sendt:",
        len(watchlist),
        "kort",
    )


def main():
    if not CANDIDATES_FILE.exists():
        print("Ingen scanner_candidates.json fundet.")
        return

    report = load_json(CANDIDATES_FILE)

    if report.get("status") not in (
        "completed",
        "api_budget_stop",
    ):
        print(
            "Scannerstatus er ikke klar:",
            report.get("status"),
        )
        return

    cards = report.get("candidates", [])

    if not isinstance(cards, list):
        raise ValueError("Ugyldigt kandidatformat")

    history_data = load_json(HISTORY_FILE)

    watchlist = build_watchlist(cards, history_data)

    send_discord(watchlist, report)


if __name__ == "__main__":
    main()
