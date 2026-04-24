from __future__ import annotations

from src.fetch.data_fetch import get_topic_available_date_range
from src.report.capability_adapters import collect_basic_analysis_snapshot
from src.report.workflow.tool_schemas import (
    validate_basic_analysis_snapshot,
    validate_fetch_availability_output,
)


def test_fetch_availability_output_contract():
    payload = get_topic_available_date_range("nonexistent-topic-for-contract-test")
    assert isinstance(payload, dict)
    validate_fetch_availability_output(payload)


def test_basic_analysis_snapshot_contract():
    snapshot = collect_basic_analysis_snapshot(
        "nonexistent-topic-for-contract-test",
        "2020-01-01",
        "2020-01-01",
        topic_label="contract-test",
    )
    assert isinstance(snapshot, dict)
    validate_basic_analysis_snapshot(snapshot)

