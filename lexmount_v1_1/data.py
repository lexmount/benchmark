"""Versioned encrypted tasks; solver receives only the rendered instruction."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from frameworks import load_tasks

ROOT = Path(__file__).resolve().parent.parent
BENCHMARK = "BU_Bench_V1_1"


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode()
    ).hexdigest()


def context(start):
    anchor = datetime.fromisoformat(start)
    if anchor.tzinfo is None:
        raise ValueError("--run-start must include a timezone")
    day = anchor.astimezone(ZoneInfo("America/New_York")).date()
    return {
        "benchmark": BENCHMARK,
        "version": "1.1.0",
        "run_started_at_utc": anchor.astimezone(UTC).isoformat(),
        "window_start_date": str(day - timedelta(days=2)),
        "window_end_date": str(day - timedelta(days=1)),
        "region": "US",
        "currency": "USD",
        "viewport": {"width": 1440, "height": 900},
    }


def tasks(start):
    meta = json.loads((ROOT / "lexmount_v1_1/manifest.json").read_text())
    actual = hashlib.sha256((ROOT / (BENCHMARK + ".enc")).read_bytes()).hexdigest()
    if actual != meta["encrypted_sha256"]:
        raise ValueError("Encrypted dataset checksum mismatch")
    rows = load_tasks(BENCHMARK)
    if len(rows) != 100 or len({t["task_id"] for t in rows}) != 100:
        raise ValueError("Expected 100 distinct task IDs")
    if [t["ordinal"] for t in rows] != list(range(1, 101)):
        raise ValueError("Dataset order changed; do not interleave this revision again")
    if digest([t["task_id"] for t in rows]) != meta["ordered_ids_sha256"]:
        raise ValueError("Task identity/order mismatch")
    ctx = context(start)
    for t in rows:
        for key, value in ctx.items():
            t["confirmed_task"] = t["confirmed_task"].replace(
                "{{" + key + "}}", str(value)
            )
        if "{{" in t["confirmed_task"] or "}}" in t["confirmed_task"]:
            raise ValueError("Unbound task parameter")
    return rows


def select(rows, ordinals=None, limit=None):
    if ordinals:
        if len(set(ordinals)) != len(ordinals) or any(
            i < 1 or i > 100 for i in ordinals
        ):
            raise ValueError("--cases requires unique original ordinals from 1 to 100")
        selected = [rows[i - 1] for i in ordinals]
    else:
        selected = list(rows)
    if limit is not None:
        if limit < 1:
            raise ValueError("--tasks must be positive")
        selected = selected[:limit]
    return selected
