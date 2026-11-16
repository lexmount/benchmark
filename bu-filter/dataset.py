"""The sole BU-filter task loader. Task text stays encrypted in the checkout.

The encryption follows the upstream anti-indexing format; it is not an access
control. The evaluator must keep the full dataset outside each actor sandbox.
"""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken

DATA_DIR = Path(__file__).resolve().parent / "data"
BENCHMARK = "BU_FILTER"
TASK_COUNT = 87
MANIFEST_SHA256 = "58421b5b6da57e1a56d7119605baaeed3869dd316e1432b5f548985ec1839505"
EXCLUDED_IDS = frozenset(['0a58ebe0-9d6c-4839-9b09-d909271bb1f9', '13cfb151-3b2c-4e4c-9632-d3145a4b63ad', '1bab296c-8836-453f-9008-5e5cae260cea', '1fd2d69b-5d3f-4d1e-8e29-4dddced1868b', '7966e6bd-f197-43d0-9ee5-88fab61c8c36', 'a4662c0f-1cb1-4208-a6bb-932735a3f007', 'a78f98be-efef-4d24-b826-c6d4f2cb93e6', 'd19f3978-9b9f-403f-a09c-936d41fd56fc', 'd61e1671-f68b-4c9a-bf8a-ef437f17901c', 'd919dc4d-dc69-431c-8af3-e52d849b9810', 'f2366e2e-ab84-4739-a493-3e81c091e00c', 'f924e084-8cd6-4ef2-8fb6-68277ffe68ea', 'fadd935f-d3dd-4c03-8366-bd7e7c146581'])
TASK_19_ID = "d7eea2b1-7d31-425e-977c-b803ffd28250"


class DatasetError(ValueError):
    """The fixed task set or an actor task no longer matches BU-filter."""


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


def _manifest() -> dict:
    raw = (DATA_DIR / "manifest.json").read_bytes()
    if _sha(raw) != MANIFEST_SHA256:
        raise DatasetError("BU-filter manifest checksum mismatch")
    manifest = json.loads(raw)
    if manifest["name"] != "BU-filter" or manifest["task_count"] != TASK_COUNT:
        raise DatasetError("Only the fixed BU-filter 87-task dataset is supported")
    return manifest


def _load() -> tuple[dict, list[dict]]:
    manifest = _manifest()
    excluded_raw = (DATA_DIR / "exclusions.json").read_bytes()
    if _sha(excluded_raw) != manifest["exclusions_sha256"]:
        raise DatasetError("BU-filter exclusions checksum mismatch")
    excluded = json.loads(excluded_raw)
    if len(excluded) != 13 or {row["task_id"] for row in excluded} != EXCLUDED_IDS:
        raise DatasetError("BU-filter must exclude exactly the approved 13 task IDs")
    encrypted = (DATA_DIR / "BU_FILTER.enc").read_bytes()
    if _sha(encrypted) != manifest["encrypted_sha256"]:
        raise DatasetError("BU-filter encrypted dataset checksum mismatch")
    key = base64.urlsafe_b64encode(hashlib.sha256(BENCHMARK.encode()).digest())
    try:
        payload = Fernet(key).decrypt(base64.b64decode(encrypted, validate=False))
        rows = json.loads(payload)
    except (InvalidToken, ValueError, TypeError) as error:
        raise DatasetError("BU-filter encrypted dataset is invalid") from error
    expected = manifest["tasks"]
    if not isinstance(rows, list) or len(rows) != TASK_COUNT or len(expected) != TASK_COUNT:
        raise DatasetError("BU-filter requires exactly 87 tasks")
    seen = set()
    excluded_ordinals = {row["original_ordinal"] for row in excluded}
    expected_ordinals = [n for n in range(1, 101) if n not in excluded_ordinals]
    if [row.get("ordinal") for row in rows] != expected_ordinals:
        raise DatasetError("BU-filter task order or original ordinals changed")
    for row, record in zip(rows, expected, strict=True):
        if set(row) != {"ordinal", "id", "instruction", "start_url", "answer"}:
            raise DatasetError("Unexpected dataset fields")
        if type(row["ordinal"]) is not int or not isinstance(row["id"], str):
            raise DatasetError("Invalid task identity")
        try:
            UUID(row["id"])
        except ValueError as error:
            raise DatasetError("Invalid task ID") from error
        if row["id"] in seen or row["id"] in EXCLUDED_IDS:
            raise DatasetError("Duplicate or excluded task ID")
        seen.add(row["id"])
        if row["id"] != record["id"] or row["ordinal"] != record["ordinal"]:
            raise DatasetError("BU-filter task identity/order mismatch")
        if not isinstance(row["instruction"], str) or not row["instruction"].strip():
            raise DatasetError("Missing task instruction")
        if row["start_url"] is not None and not isinstance(row["start_url"], str):
            raise DatasetError("Invalid task start URL")
        if row["answer"] is not None and not isinstance(row["answer"], str):
            raise DatasetError("Invalid judge reference")
        if _sha(row["instruction"].encode()) != record["instruction_sha256"]:
            raise DatasetError("Task instruction changed")
        public = {key: row[key] for key in ("id", "instruction", "start_url")}
        if _sha(_canonical(public)) != record["actor_record_sha256"]:
            raise DatasetError("Actor task changed")
    if TASK_19_ID not in seen or not any(row["ordinal"] == 19 and row["id"] == TASK_19_ID for row in rows):
        raise DatasetError("Task 19 must remain in BU-filter")
    if sum(row["answer"] is not None for row in rows) != manifest["reference_answer_count"]:
        raise DatasetError("Judge reference count changed")
    return manifest, rows


def load_tasks() -> list[dict]:
    """Return 87 public records, with original ordinal but without judge answers."""
    _, rows = _load()
    return [{key: row[key] for key in ("ordinal", "id", "instruction", "start_url")} for row in rows]


def load_judge_tasks() -> list[dict]:
    """Return 87 full records. Never expose this result to an actor."""
    return _load()[1]


def actor_task(task: dict) -> dict:
    """Validate and project one allowed task to the actor's exact three fields."""
    candidate = {key: task[key] for key in ("id", "instruction", "start_url")}
    record = next((row for row in _manifest()["tasks"] if row["id"] == candidate["id"]), None)
    if record is None or candidate["id"] in EXCLUDED_IDS:
        raise DatasetError("Task is not in the BU-filter allowlist")
    if _sha(_canonical(candidate)) != record["actor_record_sha256"]:
        raise DatasetError("Actor task differs from the frozen BU-filter instruction")
    return candidate


def validate_dataset() -> dict:
    """Validate the dataset and return provenance/counts without task or gold text."""
    manifest, rows = _load()
    return {
        "name": manifest["name"],
        "version": manifest["version"],
        "task_count": len(rows),
        "excluded_count": len(EXCLUDED_IDS),
        "reference_answer_count": manifest["reference_answer_count"],
        "task_19_retained": True,
        "manifest_sha256": MANIFEST_SHA256,
        "encrypted_sha256": manifest["encrypted_sha256"],
        "source_sha256": manifest["source_sha256"],
    }


if __name__ == "__main__":
    print(json.dumps(validate_dataset(), ensure_ascii=False, indent=2))
