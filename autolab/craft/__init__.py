"""Load montage craft templates and CapCut-style AutoCut presets."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
PRESETS_DIR = Path(__file__).resolve().parent / "presets"


def _load_dir(directory: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not directory.exists():
        return out
    for p in sorted(directory.glob("*.json")):
        out.append(json.loads(p.read_text(encoding="utf-8")))
    return out


def list_templates() -> list[str]:
    return sorted(p.stem for p in TEMPLATES_DIR.glob("*.json"))


def list_presets() -> list[str]:
    if not PRESETS_DIR.exists():
        return []
    return sorted(p.stem for p in PRESETS_DIR.glob("*.json"))


def load_template(name: str) -> dict[str, Any]:
    for directory in (TEMPLATES_DIR, PRESETS_DIR):
        path = directory / f"{name}.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        if not directory.exists():
            continue
        for p in directory.glob("*.json"):
            data = json.loads(p.read_text(encoding="utf-8"))
            if data.get("id") == name:
                return data
    raise FileNotFoundError(f"craft template/preset not found: {name}")


def all_templates() -> list[dict[str, Any]]:
    return _load_dir(TEMPLATES_DIR)


def all_presets() -> list[dict[str, Any]]:
    return _load_dir(PRESETS_DIR)


def all_craft() -> list[dict[str, Any]]:
    """Templates + AutoCut presets for competitive tournaments."""
    return all_templates() + all_presets()
