import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(Path(__file__).resolve().parents[2] / ".env")
c = OpenAI(base_url="https://api.vultrinference.com/v1", api_key=os.environ["VULTR_API_KEY"])
try:
    r = c.chat.completions.create(
        model="vultr/VultronRetrieverCore-Qwen3.5-4.5B",
        messages=[
            {
                "role": "user",
                "content": (
                    "Extract the ticket volume from: annual tickets 480000. "
                    'Reply with JSON only: {"annual_ticket_volume": number}'
                ),
            }
        ],
        max_tokens=200,
        temperature=0.2,
    )
    print(r.model_dump_json(indent=2))
except Exception as e:
    print(type(e).__name__, ":", e)
