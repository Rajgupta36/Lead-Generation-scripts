from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from leadgen.meeting_orchestrator import run_meeting_orchestrator


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate meeting-ready outreach queue from lead CSV outputs.")
    parser.add_argument("--input-dir", default="data/output-website-opportunity-flow")
    parser.add_argument("--out", default="data/output-lead-to-meeting-orchestrator")
    parser.add_argument("--max-leads", type=int, default=100)
    parser.add_argument("--crawl-workers", type=int, default=8)
    args = parser.parse_args()

    count, queue_path = run_meeting_orchestrator(
        input_dir=Path(args.input_dir),
        out_dir=Path(args.out),
        max_leads=args.max_leads,
        crawl_workers=args.crawl_workers,
    )
    print(f"Generated {count} meeting queue rows")
    print(f"Queue: {queue_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
