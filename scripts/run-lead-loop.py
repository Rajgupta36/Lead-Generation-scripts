from __future__ import annotations

import argparse
import fcntl
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "config/lead-loop.json"
LOOP_DIR = REPO_ROOT / "data/continuous-leads"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run all three lead workflows repeatedly."
    )
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval-minutes", type=int, default=None)
    parser.add_argument("--max-cycles", type=int, default=None)
    args = parser.parse_args()

    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    interval_minutes = args.interval_minutes or int(config["interval_minutes"])
    LOOP_DIR.mkdir(parents=True, exist_ok=True)
    with (LOOP_DIR / "lead-loop.lock").open("w", encoding="utf-8") as lock_handle:
        try:
            fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("The lead loop is already running.")
            return 0

        completed = 0
        while True:
            started = datetime.now(timezone.utc).isoformat()
            print(f"Starting parallel lead cycle at {started}", flush=True)
            result = subprocess.run(
                ["pnpm", "generate:lead-workflows"],
                cwd=REPO_ROOT,
                check=False,
            )
            completed += 1
            if result.returncode:
                print(f"Lead cycle failed with exit code {result.returncode}", flush=True)
            if args.once or (args.max_cycles and completed >= args.max_cycles):
                return result.returncode
            print(f"Next cycle in {interval_minutes} minutes", flush=True)
            time.sleep(interval_minutes * 60)


if __name__ == "__main__":
    raise SystemExit(main())
