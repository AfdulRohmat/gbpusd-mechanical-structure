from pathlib import Path

import pytest

from gbpusd_structure.paths import find_project_root

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_find_project_root_from_nested_directory() -> None:
    assert find_project_root(PROJECT_ROOT / "src/gbpusd_structure") == PROJECT_ROOT


def test_find_project_root_rejects_unrelated_tree(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Could not find"):
        find_project_root(tmp_path)
