"""CLI runner — drives the unified pipeline core with a printing emitter.

Usage:
  python backend/pipeline/run_category.py [customer_support|marketing|maintenance]

Defaults to customer_support. Prints the live stage log, then the assembled
text memo, and writes the memo to backend/pipeline/last_memo_<category>.txt.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from agents.report import assemble_memo  # noqa: E402
from pipeline.core import CATEGORIES, load_default_company, run  # noqa: E402
from pipeline.events import PrintingEmitter  # noqa: E402


def main(category_key: str) -> str:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    company = load_default_company(category_key)

    # Sequential branches so the printed stage log stays readable.
    result = run(category_key, company, emitter=PrintingEmitter(), parallel=False)

    memo_text = assemble_memo(
        company=result.company,
        plan=result.plan,
        branch_plan=result.branch_plan,
        branch_results=result.branch_results,
        recommendation=result.memo.get("recommendation"),
    )
    print("\n" + "=" * 72)
    print("FINAL MEMO")
    print("=" * 72)
    print(memo_text)

    out_path = ROOT / "backend" / "pipeline" / f"last_memo_{category_key}.txt"
    out_path.write_text(memo_text, encoding="utf-8")
    print(f"\nMemo written to {out_path}")
    return memo_text


if __name__ == "__main__":
    cat = sys.argv[1] if len(sys.argv) > 1 else "customer_support"
    if cat not in CATEGORIES:
        print(f"Usage: python run_category.py [{' | '.join(CATEGORIES.keys())}]")
        sys.exit(1)
    try:
        main(cat)
    except Exception as exc:
        print(f"\nPIPELINE FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
