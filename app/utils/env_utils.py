"""Helpers for updating .env style files safely."""

from __future__ import annotations

import os
from pathlib import Path


def upsert_env_values(env_file: str, values: dict[str, str]) -> None:
    path = Path(env_file)
    path.parent.mkdir(parents=True, exist_ok=True)

    lines = []
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"

    normalized_values = {str(key): str(value) for key, value in values.items()}
    updated_keys = set()
    new_lines = []

    for line in lines:
        replaced = False
        for key, value in normalized_values.items():
            target_prefix = f"{key}="
            if line.startswith(target_prefix):
                new_lines.append(f"{target_prefix}{value}\n")
                updated_keys.add(key)
                replaced = True
                break
        if not replaced:
            new_lines.append(line)

    for key, value in normalized_values.items():
        if key in updated_keys:
            continue
        new_lines.append(f"{key}={value}\n")

    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text("".join(new_lines), encoding="utf-8")
    os.replace(temp_path, path)


def upsert_env_value(env_file: str, key: str, value: str) -> None:
    upsert_env_values(env_file, {key: value})
