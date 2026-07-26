from __future__ import annotations

import csv
import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class City:
    city: str
    country: str
    region: str = ""


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    for key, value in values.items():
        os.environ.setdefault(key, value)
    return values


def load_cities(path: Path) -> list[City]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return [
            City(
                city=(row.get("city") or "").strip(),
                country=(row.get("country") or "").strip(),
                region=(row.get("region") or "").strip(),
            )
            for row in reader
            if (row.get("city") or "").strip() and (row.get("country") or "").strip()
        ]


def load_industries(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def load_dorks(path: Path) -> dict[str, list[str]]:
    text = path.read_text(encoding="utf-8")
    stripped = text.lstrip()
    if stripped.startswith("{"):
        data = json.loads(text)
        return {str(k): [str(item) for item in v] for k, v in data.items()}

    dorks: dict[str, list[str]] = {}
    current: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped_line = line.strip()
        if not stripped_line or stripped_line.startswith("#"):
            continue
        if not line.startswith((" ", "\t")) and stripped_line.endswith(":"):
            current = stripped_line[:-1].strip()
            dorks.setdefault(current, [])
            continue
        if current and stripped_line.startswith("- "):
            item = stripped_line[2:].strip()
            if (item.startswith("'") and item.endswith("'")) or (
                item.startswith('"') and item.endswith('"')
            ):
                item = item[1:-1]
            dorks[current].append(item)
    return {segment: templates for segment, templates in dorks.items() if templates}
