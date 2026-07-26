from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python3 scripts/run-flow.py <flow.json>", file=sys.stderr)
        return 2

    flow_path = Path(sys.argv[1]).resolve()
    repo_root = Path(__file__).resolve().parents[1]
    config = json.loads(flow_path.read_text(encoding="utf-8"))

    args = [sys.executable, "-m", "leadgen", config.get("command", "run")]
    if config.get("action"):
        args.append(str(config["action"]))
    for key, value in config.get("args", {}).items():
        flag = f"--{key.replace('_', '-')}"
        if isinstance(value, bool):
            if value:
                args.append(flag)
            continue
        if value is None:
            continue
        args.extend([flag, str(value)])

    print(f"Running flow: {config.get('name', flow_path.parent.name)}")
    print(" ".join(args))
    return subprocess.run(args, cwd=repo_root).returncode


if __name__ == "__main__":
    raise SystemExit(main())
