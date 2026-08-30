from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from gbpusd_structure.config import load_project_config
from gbpusd_structure.data import REQUIRED_M5_COLUMNS, audit_canonical_m5, iter_months

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_iter_months_uses_half_open_interval() -> None:
    assert iter_months(datetime(2024, 1, 1).date(), datetime(2024, 3, 1).date()) == (
        "2024-01",
        "2024-02",
    )


def test_audit_one_month_contract(tmp_path: Path) -> None:
    config = load_project_config(PROJECT_ROOT / "config")
    research = config.research.model_copy(
        update={
            "periods": config.research.periods.model_copy(
                update={
                    "research_start": datetime(2024, 1, 1).date(),
                    "construction_end": datetime(2024, 1, 15).date(),
                    "replication_end": datetime(2024, 2, 1).date(),
                    "research_end": datetime(2024, 2, 1).date(),
                }
            )
        }
    )
    timestamp = pd.to_datetime([datetime(2024, 1, 2, tzinfo=UTC)], utc=True)
    content = {column: [1.27] for column in REQUIRED_M5_COLUMNS}
    content["timestamp"] = timestamp
    content["tick_count"] = [10]
    content["activity_count"] = [10]
    content["spread_median_pips"] = [0.8]
    content["spread_p95_pips"] = [1.0]
    content["spread_max_pips"] = [1.2]
    content["first_tick_timestamp"] = timestamp
    content["last_tick_timestamp"] = timestamp
    path = (
        tmp_path
        / "processed/m5_monthly/symbol=GBPUSD/year=2024/m5-2024-01.parquet"
    )
    path.parent.mkdir(parents=True)
    pd.DataFrame(content).to_parquet(path, index=False)

    summary = audit_canonical_m5(tmp_path, research)

    assert summary["valid"] is True
    assert summary["bar_count"] == 1
    assert summary["spread_median_pips"] == 0.8
