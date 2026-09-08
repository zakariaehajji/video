"""Load montage craft templates and apply them to story planning."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


def list_templates() -> list[str]:
    return sorted(p.stem for p in TEMPLATES_DIR.glob("*.json"))


def load_template(name: str) -> dict[str, Any]:
    path = TEMPLATES_DIR / f"{name}.json"
    if not path.exists():
        # allow id field match
        for p in TEMPLATES_DIR.glob("*.json"):
            data = json.loads(p.read_text(encoding="utf-8"))
            if data.get("id") == name:
                return data
        raise FileNotFoundError(f"craft template not found: {name}")
    return json.loads(path.read_text(encoding="utf-8"))


def all_templates() -> list[dict[str, Any]]:
    out = []
    for p in sorted(TEMPLATES_DIR.glob("*.json")):
        out.append(json.loads(p.read_text(encoding="utf-8")))
    return out
