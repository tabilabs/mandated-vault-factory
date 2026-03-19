from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml


def get_predict_root() -> Path:
    return Path(__file__).resolve().parents[1]


LIB_DIR = get_predict_root() / "lib"
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))


def parse_env_file_keys(env_path: Path) -> set[str]:
    keys: set[str] = set()
    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _value = line.split("=", 1)
        keys.add(key.strip())
    return keys


def parse_skill_frontmatter(skill_path: Path) -> tuple[dict[str, Any], str]:
    text = skill_path.read_text()
    if not text.startswith("---\n"):
        raise AssertionError("SKILL.md must start with YAML frontmatter")

    _start, rest = text.split("---\n", 1)
    frontmatter_text, body = rest.split("\n---\n", 1)
    frontmatter = yaml.safe_load(frontmatter_text)

    if not isinstance(frontmatter, dict):
        raise AssertionError("SKILL.md frontmatter must decode to a mapping")

    return frontmatter, body
