from __future__ import annotations

import pytest

from scripts.run_lifecycle_integrity_audit import parse_args


def test_lifecycle_runner_defaults_to_full_history():
    """B2B journeys span 6-18 months; a creation-date window is opt-in only."""
    args = parse_args([])
    assert args.days is None
    assert args.full_history is False
    assert args.include_activities is False


def test_lifecycle_runner_supports_windowed_quick_scans():
    args = parse_args(["--days", "90"])
    assert args.days == 90


def test_lifecycle_runner_supports_full_history_and_activity_metadata():
    args = parse_args(["--full-history", "--include-activities"])
    assert args.full_history is True
    assert args.include_activities is True


def test_lifecycle_runner_rejects_conflicting_windows():
    with pytest.raises(SystemExit):
        parse_args(["--days", "30", "--full-history"])
