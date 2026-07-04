"""Quick SSE smoke test — reads events until memo_ready or error."""

from __future__ import annotations

import json
import sys
import urllib.request

URL = "http://127.0.0.1:8001/api/run/stream?category=marketing&company_id=novavita-dtc-marketing"


def main() -> int:
    req = urllib.request.Request(URL, headers={"Accept": "text/event-stream"})
    events: list[str] = []
    with urllib.request.urlopen(req, timeout=600) as resp:
        for raw_line in resp:
            line = raw_line.decode().strip()
            if not line.startswith("data:"):
                continue
            payload = json.loads(line[5:].strip())
            event = payload.get("event")
            events.append(event)
            print(event, flush=True)
            if event in ("memo_ready", "error"):
                break
    if events[-1] != "memo_ready":
        print("Expected memo_ready", events, file=sys.stderr)
        return 1
    print(f"OK — {len(events)} events", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
