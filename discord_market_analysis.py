import json
import os
from pathlib import Path
from datetime import datetime, timezone

import requests

WEBHOOK = os.environ.get('DISCORD_MARKET_ANALYSIS_WEBHOOK', '').strip()
REPORT = Path('scanner_candidates.json')
MAX_CARDS = 10


def main():
    if not WEBHOOK:
        print('DISCORD_MARKET_ANALYSIS_WEBHOOK mangler - springer over.')
        return
    if not REPORT.exists():
        print('Ingen scanner_candidates.json - springer over.')
        return
    report = json.loads(REPORT.read_text(encoding='utf-8'))
    if report.get('status') not in ('completed', 'api_budget_stop'):
        print('Scannerstatus er ikke klar:', report.get('status'))
        return
    cards = report.get('candidates', [])
    if not isinstance(cards, list):
        raise ValueError('Ugyldigt kandidatformat')
    valid = []
    for card in cards:
        try:
            price = float(card['market_price_usd'])
            listings = int(card.get('total_listings') or 0)
            if 5 <= price <= 200 and listings >= 0:
                valid.append((card, price, listings))
        except (KeyError, ValueError, TypeError):
            continue
    # Prioriter likviditetsindikatoren, men kald det ikke et koebssignal.
    valid.sort(key=lambda x: (-x[2], x[1]))
    top = valid[:MAX_CARDS]
    if not top:
        print('Ingen kort til markedsanalyse.')
        return
    lines = []
    for i, (card, price, listings) in enumerate(top, 1):
        name = str(card.get('name', 'Ukendt'))[:100]
        set_name = str(card.get('set_name', 'Ukendt saet'))[:90]
        lines.append(f'**{i}. {name}**\n{set_name} | **${price:.2f}** | {listings} annoncer')
    generated = str(report.get('generated_at') or '')[:10]
    payload = {
        'username': 'PokeWatch Market Analysis',
        'embeds': [{
            'title': '📊 PokéWatch | RAW Market Overview',
            'description': '\n\n'.join(lines)[:3900],
            'color': 3447003,
            'fields': [
                {'name': 'Scannerstatus', 'value': str(report.get('status')), 'inline': True},
                {'name': 'RAW-kandidater', 'value': str(report.get('total_candidates', len(cards))), 'inline': True},
                {'name': 'Dato', 'value': generated or datetime.now(timezone.utc).date().isoformat(), 'inline': True}
            ],
            'footer': {'text': 'Sorteret efter antal annoncer. Ikke investeringsanbefalinger; prisudvikling er endnu ikke vurderet.'}
        }]
    }
    response = requests.post(WEBHOOK, json=payload, timeout=20)
    response.raise_for_status()
    print('Market Analysis sendt:', len(top), 'kort')


if __name__ == '__main__':
    main()
