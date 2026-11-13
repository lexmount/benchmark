"""Private append-only run artifacts. No keys or Authorization headers are saved."""

import json
import os
import re
from pathlib import Path


def redact(text):
    text = str(text)
    for key, value in os.environ.items():
        if len(value) >= 8 and any(
            s in key.upper() for s in ("API_KEY", "TOKEN", "PASSWORD", "SECRET")
        ):
            text = text.replace(value, "[REDACTED]")
    return re.sub(r"sk-[A-Za-z0-9_-]{8,}", "[REDACTED]", text)


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write("\n")


def read(path):
    return json.loads(Path(path).read_text())
