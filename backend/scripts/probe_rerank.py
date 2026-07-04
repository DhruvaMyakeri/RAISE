import json
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")
key = os.environ["VULTR_API_KEY"]
r = httpx.post(
    "https://api.vultrinference.com/v1/rerank",
    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    json={
        "model": "vultr/VultronRetrieverCore-Qwen3.5-4.5B",
        "query": "Tier-1 ticket deflection rate for customer support AI",
        "documents": [
            "Company claims 50% Tier-1 deflection.",
            "Industry chatbots resolve about 68% of Tier-1 tickets.",
            "Weather is sunny today.",
        ],
        "top_n": 3,
    },
    timeout=60.0,
)
print(r.status_code)
print(json.dumps(r.json(), indent=2))
