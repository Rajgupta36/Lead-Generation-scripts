from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from leadgen.report import generate_reports


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate revenue-focused mini-audits from lead CSV exports.")
    parser.add_argument("--input-dir", default="data/output-website-opportunity-flow")
    parser.add_argument("--out", default="data/reports/personalized-audit-report-flow")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    count, summary_path = generate_reports(Path(args.input_dir), Path(args.out), args.limit)
    print(f"Generated {count} audit reports")
    print(f"Summary: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
