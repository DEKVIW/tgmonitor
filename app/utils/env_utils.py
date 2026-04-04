"""Helpers for updating .env style files safely."""

from __future__ import annotations

import os
from pathlib import Path


def upsert_env_value(env_file: str, key: str, value: str) -> None:
    path = Path(env_file)
    path.parent.mkdir(parents=True, exist_ok=True)

    lines = []
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"

    target_prefix = f"{key}="
    updated = False
    new_lines = []

    for line in lines:
        if line.startswith(target_prefix):
            new_lines.append(f"{target_prefix}{value}\n")
            updated = True
        else:
            new_lines.append(line)

    if not updated:
        new_lines.append(f"{target_prefix}{value}\n")

    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text("".join(new_lines), encoding="utf-8")
    os.replace(temp_path, path)
