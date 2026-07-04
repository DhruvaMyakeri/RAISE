import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
load_dotenv(ROOT / ".env")

from config.models import PLANNER_MODEL
from config.token_budgets import PLANNER

company = json.loads((ROOT / "data/companies/meridian_support.json").read_text())
client = OpenAI(base_url="https://api.vultrinference.com/v1", api_key=os.environ["VULTR_API_KEY"])
r = client.chat.completions.create(
    model=PLANNER_MODEL,
    messages=[
        {
            "role": "user",
            "content": (
                "Respond with JSON ONLY: "
                '{"category":"Customer Support AI","roi_dimensions":["Cost impact"],'
                '"missing_fields":["hosting_architecture"],'
                '"clarifying_question":"On-prem or cloud?","question_field":"hosting_architecture"}\n'
                f"Company: {json.dumps(company)[:500]}"
            ),
        }
    ],
    max_tokens=PLANNER["max_tokens"],
    temperature=0.2,
)
print(r.model_dump_json(indent=2))
