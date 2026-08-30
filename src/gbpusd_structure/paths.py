"""Project path helpers."""

from pathlib import Path


def find_project_root(start: Path) -> Path:
    current = start.resolve()
    for candidate in (current, *current.parents):
        if (candidate / "pyproject.toml").is_file():
            return candidate
    raise ValueError(f"Could not find pyproject.toml from {start}")
