
import os
import json
import requests

API_KEY = os.environ.get("TCG_API_KEY")

if not API_KEY:
    raise RuntimeError("TCG_API_KEY mangler.")

url = "https://api.tcgapi.dev/v1/prices/top-movers"

response = requests.get(
    url,
    headers={"X-API-Key": API_KEY},
    timeout=30,
)

response.raise_for_status()
data = response.json()

print("API-forbindelse: OK")
print("Svar-type:", type(data).__name__)

if isinstance(data, dict):
    print("Tilgængelige felter:", list(data.keys()))

    for key, value in data.items():
        if isinstance(value, list):
            print(f"{key}: {len(value)} resultater")

            if value:
                print(
                    "Felter i første resultat:",
                    list(value[0].keys())
                    if isinstance(value[0], dict)
                    else type(value[0]).__name__
                )
else:
    print("Antal resultater:", len(data))

print("Scanner-test afsluttet.")
