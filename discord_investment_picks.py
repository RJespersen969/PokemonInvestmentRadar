
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

# PokeWatch - Discord Investment Picks V1.0
# Sender kun nye prisfald med mindst 7 dages prishistorik.

WEBHOOK = os.environ.get("DISCORD_INVESTMENT_WEBHOOK", "").strip()

REPORT_FILE = Path("scanner_candidates.json")
HISTORY_FILE = Path("scanner_price_history.json")
ALERT_FILE = Path("discord_alert_state.json")

MIN_DROP_PERCENT = 10
MIN_HISTORY_DAYS = 7
MAX_ALERTS_PER_RUN = 5


def load_json(path, default):
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def main():
    print("=== POKEWATCH DISCORD INVESTMENT PICKS ===")

    if not WEBHOOK:
        raise RuntimeError(
            "DISCORD_INVESTMENT_WEBHOOK mangler i GitHub Secrets."
        )

    report = load_json(REPORT_FILE, {})
    history = load_json(HISTORY_FILE, {})
    alert_state = load_json(ALERT_FILE, {"sent": {}})

    if not isinstance(alert_state.get("sent"), dict):
        raise ValueError("Ugyldig Discord alert state.")

    status = report.get("status")

    if status != "completed":
        print("Scannerstatus:", status)
        print("Ingen Discord-fund sendt.")
        return

    candidates = report.get("candidates", [])
    observations = history.get("observations", {})

    if not isinstance(candidates, list):
        raise ValueError("Ugyldig kandidatliste.")

    if not isinstance(observations, dict):
        raise ValueError("Ugyldig prishistorik.")

    today = datetime.now(timezone.utc).date()
    cutoff = today - timedelta(days=MIN_HISTORY_DAYS)

    picks = []

    for card in candidates:
        if not isinstance(card, dict):
            continue

        card_id = card.get("card_id")
        printing = card.get("printing") or "Unknown"

        if card_id is None:
            continue

        key = f"{card_id}:{printing}"
        entry = observations.get(key, {})
        prices = entry.get("prices", [])

        if not isinstance(prices, list):
            continue

        valid = []

        for observation in prices:
            try:
                date = datetime.strptime(
                    observation["date"], "%Y-%m-%d"
                ).date()

                price = float(observation["market_price_usd"])

                if price > 0:
                    valid.append((date, price))
            except (KeyError, TypeError, ValueError):
                continue

        if not valid:
            continue

        valid.sort(key=lambda item: item[0])

        # Vi sender kun fund med en observation fra i dag.
        latest_date, latest_price = valid[-1]

        if latest_date != today:
            continue

        older = [
            item for item in valid
            if item[0] <= cutoff
        ]

        if not older:
            continue

        old_date, old_price = older[-1]

        change = (latest_price - old_price) / old_price * 100

        if change > -MIN_DROP_PERCENT:
            continue

        # Et fund sendes højst én gang for samme prisdato.
        alert_key = f"{key}:{latest_date.isoformat()}"

        if alert_key in alert_state["sent"]:
            continue

        picks.append({
            "key": alert_key,
            "name": str(card.get("name") or "Ukendt kort"),
            "set": str(card.get("set_name") or "Ukendt sæt"),
            "printing": printing,
            "old_price": old_price,
            "price": latest_price,
            "change": change,
            "history_date": old_date.isoformat(),
        })

    picks.sort(key=lambda item: item["change"])
    picks = picks[:MAX_ALERTS_PER_RUN]

    print("Nye mulige investeringsfund:", len(picks))

    if not picks:
        print("Ingen nye fund med tilstrækkelig prishistorik.")
        return

    for card in picks:
        message = {
            "username": "PokeWatch Investment Radar",
            "embeds": [
                {
                    "title": "🎯 PokeWatch - Muligt prisfald",
                    "description": (
                        f"**{card['name']}**\n"
                        f"{card['set']} | {card['printing']}"
                    ),
                    "color": 3447003,
                    "fields": [
                        {
                            "name": "Aktuel markedspris",
                            "value": f"${card['price']:.2f} USD",
                            "inline": True
                        },
                        {
                            "name": "Prisændring",
                            "value": f"{card['change']:.1f}%",
                            "inline": True
                        },
                        {
                            "name": "Tidligere pris",
                            "value": (
                                f"${card['old_price']:.2f} USD "
                                f"({card['history_date']})"
                            ),
                            "inline": False
                        }
                    ],
                    "footer": {
                        "text": (
                            "TCGPlayer-markedsdata via TCG API. "
                            "Prisfald er ikke en købsanbefaling."
                        )
                    }
                }
            ]
        }

        response = requests.post(
            WEBHOOK,
            json=message,
            timeout=20
        )
        response.raise_for_status()

        # Gem straks efter vellykket afsendelse.
        alert_state["sent"][card["key"]] = today.isoformat()

        with ALERT_FILE.open("w", encoding="utf-8") as file:
            json.dump(
                alert_state,
                file,
                indent=2,
                ensure_ascii=False
            )

        print("Discord sendt:", card["name"])

    print("Discord Investment Picks afsluttet.")


if __name__ == "__main__":
    main()
