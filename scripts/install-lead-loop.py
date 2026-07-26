from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
LABEL = "com.nexstudio.lead-loop"
PLIST_PATH = Path.home() / "Library/LaunchAgents" / f"{LABEL}.plist"


def main() -> int:
    pnpm = shutil.which("pnpm")
    if not pnpm:
        raise SystemExit("pnpm was not found in PATH")
    config = __import__("json").loads(
        (REPO_ROOT / "config/lead-loop.json").read_text(encoding="utf-8")
    )
    interval_seconds = int(config["interval_minutes"]) * 60
    output_dir = REPO_ROOT / "data/continuous-leads"
    output_dir.mkdir(parents=True, exist_ok=True)
    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)

    environment_path = ":".join(
        dict.fromkeys(
            [
                str(Path(pnpm).parent),
                "/opt/homebrew/bin",
                "/usr/local/bin",
                "/usr/bin",
                "/bin",
            ]
        )
    )
    payload = {
        "Label": LABEL,
        "ProgramArguments": [
            sys.executable,
            str(REPO_ROOT / "scripts/run-lead-loop.py"),
            "--once",
        ],
        "WorkingDirectory": str(REPO_ROOT),
        "EnvironmentVariables": {
            "PATH": environment_path,
            "HOME": str(Path.home()),
        },
        "StartInterval": interval_seconds,
        "RunAtLoad": False,
        "StandardOutPath": str(output_dir / "scheduler.log"),
        "StandardErrorPath": str(output_dir / "scheduler-error.log"),
        "ProcessType": "Background",
    }
    with PLIST_PATH.open("wb") as handle:
        plistlib.dump(payload, handle, sort_keys=True)

    service = f"gui/{os.getuid()}"
    subprocess.run(
        ["launchctl", "bootout", service, str(PLIST_PATH)],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.run(
        ["launchctl", "bootstrap", service, str(PLIST_PATH)],
        check=True,
    )
    print(f"Installed {LABEL}")
    print(f"Schedule: every {interval_seconds // 3600} hours")
    print(f"Plist: {PLIST_PATH}")
    print(f"Log: {output_dir / 'scheduler.log'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
