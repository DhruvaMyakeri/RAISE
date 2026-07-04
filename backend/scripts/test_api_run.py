"""Smoke-test POST /api/run for all three categories."""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8001"
CATEGORIES = [
    ("customer_support", "meridian-retail-support"),
    ("marketing", "novavita-dtc-marketing"),
    ("maintenance", "apex-valve-maintenance"),
]


def post_run(category: str, company_id: str) -> dict:
    body = json.dumps({"category": category, "company_id": company_id}).encode()
    req = urllib.request.Request(
        f"{BASE}/api/run",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=600) as resp:
        return json.loads(resp.read())


def summarize(memo: dict) -> dict:
    branches = memo.get("branches", [])
    lik_roi = [
        b.get("metrics", {}).get("roi_3yr", {}).get("likely")
        for b in branches
    ]
    return {
        "company": memo.get("meta", {}).get("company_name"),
        "category_key": memo.get("meta", {}).get("category_key"),
        "branch_count": len(branches),
        "likely_roi": lik_roi,
        "recommendation_winner": memo.get("recommendation", {}).get("winner"),
        "flag_types": {
            b.get("label"): list({f.get("type") for f in b.get("flagged_assumptions", [])})
            for b in branches
        },
        "explainability_dims": {
            b.get("label"): len(b.get("explainability", {}).get("dimensions", []))
            for b in branches
        },
    }


def main() -> int:
    results = {}
    for category, company_id in CATEGORIES:
        print(f"\n=== Running {category} ===", flush=True)
        try:
            memo = post_run(category, company_id)
            summary = summarize(memo)
            results[category] = summary
            print(json.dumps(summary, indent=2), flush=True)
            out = f"backend/pipeline/api_test_{category}.json"
            with open(out, "w", encoding="utf-8") as f:
                json.dump(memo, f, indent=2, default=str)
            print(f"Saved full memo to {out}", flush=True)
        except urllib.error.HTTPError as exc:
            print(f"FAILED {category}: HTTP {exc.code} {exc.read().decode()}", flush=True)
            return 1
        except Exception as exc:
            print(f"FAILED {category}: {type(exc).__name__}: {exc}", flush=True)
            return 1
    print("\n=== ALL PASSED ===", flush=True)
    print(json.dumps(results, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
