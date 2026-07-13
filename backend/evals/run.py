"""Eval runner.

    python -m evals.run --mock            # free harness smoke (CI)
    python -m evals.run --live            # real providers (capped; spends credits)
    python -m evals.run --live --only claim_validation,recommendation

Live cost cap (approx, per full run): 3 claim-validation chat calls + 9 rerank
calls + 3 explainability calls + 2 recommendation calls. Keep it nightly or
manual — do not wire --live into per-push CI.

Exit code 1 if any eval scores below its threshold (for nightly gating).
Results are appended to evals/results.jsonl.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

THRESHOLDS = {
    "claim_validation": 0.85,
    "explainability_format": 0.75,
    "recommendation_integrity": 0.85,
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Vantage LLM-behavior evals")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--live", action="store_true", help="score real provider behavior")
    mode.add_argument("--mock", action="store_true", help="harness smoke with fake providers")
    parser.add_argument("--only", default="", help="comma-separated eval names")
    args = parser.parse_args()

    if args.mock:
        from evals._common import install_mocks

        install_mocks()

    from evals import eval_claim_validation, eval_explainability, eval_recommendation

    registry = {
        "claim_validation": eval_claim_validation.run_eval,
        "explainability_format": eval_explainability.run_eval,
        "recommendation_integrity": eval_recommendation.run_eval,
    }
    selected = [s.strip() for s in args.only.split(",") if s.strip()] or list(registry)

    results = []
    for name in selected:
        if name not in registry:
            print(f"unknown eval: {name} (available: {', '.join(registry)})", file=sys.stderr)
            return 2
        print(f"running {name} ({'mock' if args.mock else 'LIVE'})...", flush=True)
        results.append(registry[name]())

    out_path = Path(__file__).parent / "results.jsonl"
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": "mock" if args.mock else "live",
        "results": [
            {
                "eval": r.eval_name,
                "score": r.score,
                "threshold": THRESHOLDS.get(r.eval_name),
                "cases": [
                    {"name": c.name, "passed": c.passed, "details": c.details} for c in r.cases
                ],
            }
            for r in results
        ],
    }
    with out_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")

    print()
    failed = False
    for r in results:
        print(r.summary())
        threshold = THRESHOLDS.get(r.eval_name, 1.0)
        if r.score < threshold:
            print(f"  -> BELOW THRESHOLD ({r.score:.0%} < {threshold:.0%})")
            failed = True
        print()
    print(f"results appended to {out_path}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
