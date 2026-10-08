
import os
import json
from datetime import datetime, timezone

import requests

API_KEY = os.environ.get("TCG_API_KEY")

def main():
    print("PokéWatch Investment Radar V1")
    print("Starter:", datetime.now(timezone.utc).isoformat())

    if not API_KEY:
        raise RuntimeError("TCG_API_KEY mangler i miljøvariablerne.")

    print("API-nøgle fundet.")
    print("Klar til første prisforespørgsel.")

if __name__ == "__main__":
    main()
