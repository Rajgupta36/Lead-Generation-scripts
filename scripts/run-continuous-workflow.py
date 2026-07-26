from __future__ import annotations

import argparse
import fcntl
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from leadgen.continuous import (
    WORKFLOWS,
    agency_has_forbidden_service,
    build_workflow_query,
    finish_workflow_state,
    load_loop_config,
    load_state,
    merge_leads,
    qualify_rows,
    read_run_events,
    read_rows,
    save_json_atomic,
    select_workflow_tasks,
    workflow_row_relevant,
    write_master_csv,
)
from leadgen.decision_makers import crawl_decision_pages
from leadgen.pipeline import run_pipeline


SEED_PATH = REPO_ROOT / "data/output-americas-email-leads-2026-07-26/all_leads.csv"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run one stateful continuous lead workflow cycle."
    )
    parser.add_argument("--workflow", choices=WORKFLOWS, required=True)
    parser.add_argument("--config", default="config/lead-loop.json")
    parser.add_argument("--out", default="data/continuous-leads")
    args = parser.parse_args()

    config = load_loop_config(REPO_ROOT / args.config)
    workflow_dir = REPO_ROOT / args.out / args.workflow
    workflow_dir.mkdir(parents=True, exist_ok=True)
    lock_path = workflow_dir / "workflow.lock"
    with lock_path.open("w", encoding="utf-8") as lock_handle:
        try:
            fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(f"{args.workflow}: another cycle is already running")
            return 0
        return run_cycle(args.workflow, config, workflow_dir)


def run_cycle(workflow: str, config: dict, workflow_dir: Path) -> int:
    state_path = workflow_dir / "state.json"
    state = load_state(state_path)
    state["last_started_at"] = datetime.now(timezone.utc).isoformat()
    state["last_status"] = "running"
    save_json_atomic(state_path, state)
    cycle = int(state["cycle"])
    tasks = select_workflow_tasks(workflow, config, state)
    staging = workflow_dir / "runs" / f"cycle-{cycle:06d}"
    staging.mkdir(parents=True, exist_ok=True)
    candidates = []
    failures = []

    workers = 3 if workflow == "businesses" else 2
    results_per_query = int(
        config.get("workflow_results_per_query", {}).get(
            workflow,
            config.get("results_per_query", 12),
        )
    )
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                run_task,
                task,
                staging / f"{index:02d}-{slug(str(task['city']))}",
                results_per_query,
                int(config.get("crawl_workers", 5)),
                cycle,
            ): task
            for index, task in enumerate(tasks, start=1)
        }
        for future in as_completed(futures):
            task = futures[future]
            try:
                rows = future.result()
                candidates.extend(rows)
                print(
                    f"{workflow}: {task['city']}, {task['country']} "
                    f"accepted {len(rows)} candidates",
                    flush=True,
                )
            except Exception as error:
                failures.append(
                    {
                        "city": task["city"],
                        "country": task["country"],
                        "error": f"{type(error).__name__}: {error}",
                    }
                )

    master_path = workflow_dir / "all_leads.csv"
    existing = read_rows(master_path)
    if not existing:
        existing = seed_rows(workflow)
    existing = [
        row for row in existing if workflow_row_relevant(row, workflow)
    ]
    limit = int(config.get("workflow_limits", {}).get(workflow, 15))
    merged, added = merge_leads(existing, candidates, limit=limit)
    write_master_csv(master_path, merged)
    write_master_csv(workflow_dir / "new_leads_latest.csv", added)

    next_state = finish_workflow_state(workflow, config, state, failures)
    next_state.update(
        {
            "last_completed_at": datetime.now(timezone.utc).isoformat(),
            "last_status": "completed" if not failures else "completed_with_errors",
            "last_new_leads": len(added),
            "last_candidates": len(candidates),
            "last_failures": failures,
            "total_leads": len(merged),
        }
    )
    save_json_atomic(state_path, next_state)
    summary = {
        "workflow": workflow,
        "cycle": cycle,
        "tasks": len(tasks),
        "candidates": len(candidates),
        "new_leads": len(added),
        "total_leads": len(merged),
        "failures": failures,
        "master_csv": str(master_path.resolve()),
    }
    save_json_atomic(workflow_dir / "latest_summary.json", summary)
    append_event(workflow_dir / "history.jsonl", summary)
    print(json.dumps(summary, indent=2), flush=True)
    return 0


def run_task(
    task: dict[str, str | int],
    out_dir: Path,
    results_per_query: int,
    crawl_workers: int,
    cycle: int,
) -> list[dict[str, str]]:
    run_pipeline(
        provider_name="serper",
        env_path=REPO_ROOT / ".env",
        cities_path=REPO_ROOT / "config/cities.csv",
        dorks_path=REPO_ROOT / "config/dorks.yaml",
        industries_path=REPO_ROOT / "config/industries.txt",
        out_dir=out_dir,
        max_queries=1,
        max_results_per_query=results_per_query,
        query=build_workflow_query(task),
        segment=str(task["segment"]),
        city=str(task["city"]),
        country=str(task["country"]),
        request_timeout_seconds=5,
        crawl_delay_seconds=0,
        max_followup_pages=1,
        max_leads=results_per_query,
        crawl_workers=crawl_workers,
        reject_junk_results=True,
    )
    search_failures = read_run_events(out_dir / "run_log.jsonl", "search_failed")
    if search_failures:
        errors = "; ".join(
            str(event.get("error", "unknown search error"))
            for event in search_failures
        )
        raise RuntimeError(f"Search provider failed: {errors}")
    rows = qualify_rows(
        read_rows(out_dir / "all_leads.csv"),
        segment=str(task["segment"]),
        region=str(task["region"]),
        cycle=cycle,
    )
    accepted = []
    for row in rows:
        workflow = str(task["workflow"])
        if not workflow_row_relevant(row, workflow):
            continue
        if workflow == "agency_partners" and not agency_services_allowed(
            row.get("website", "")
        ):
            continue
        row["workflow"] = workflow
        row["business_size_tier"] = str(task.get("business_size_tier", ""))
        accepted.append(row)
    return accepted


def agency_services_allowed(website: str) -> bool:
    documents = crawl_decision_pages(
        website,
        seed_urls=[],
        timeout_seconds=6,
        max_pages=1,
    )
    if not documents:
        return False
    return not agency_has_forbidden_service(documents[0].text)


def seed_rows(workflow: str) -> list[dict[str, str]]:
    now = datetime.now(timezone.utc).isoformat()
    seeds = []
    for row in read_rows(SEED_PATH):
        if workflow == "businesses" and row.get("segment") != "small_business":
            continue
        if workflow == "coaches" and row.get("segment") != "coach":
            continue
        if workflow == "agency_partners":
            continue
        seeded = dict(row)
        seeded.update(
            {
                "workflow": workflow,
                "business_size_tier": "small" if workflow == "businesses" else "",
                "region": "americas_seed",
                "first_seen_at": row.get("created_at") or now,
                "last_seen_at": now,
                "loop_cycle": "seed",
            }
        )
        seeds.append(seeded)
    return seeds


def append_event(path: Path, event: dict) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")


def slug(value: str) -> str:
    return re_sub_non_word(value.lower()).strip("-")


def re_sub_non_word(value: str) -> str:
    import re

    return re.sub(r"[^a-z0-9]+", "-", value)


if __name__ == "__main__":
    raise SystemExit(main())
