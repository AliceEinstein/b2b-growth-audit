"""Golden invariants for every synthetic dataset.

LLM steps are non-deterministic, so golden tests assert measurement-level
invariants and safety properties, not report text (per the design contract).
"""
from __future__ import annotations

import pytest

from core.profiler import profile_run
from core.rules import measure_all
from core.safety import EMAIL_PATTERN
from core.schemas import CrmContext
from core.synthetic_datasets import DATASETS
from core.validators import validate_phase3_artifacts


@pytest.mark.parametrize("name", sorted(DATASETS))
def test_dataset_measurement_invariants(tmp_path, name):
    run, context_data, expects = DATASETS[name](tmp_path)
    profile_run(run)
    results = measure_all(run, CrmContext.model_validate(context_data))

    lookup = {
        (module, m["id"]): m
        for module, doc in results.items()
        for m in doc["measurements"]
    }
    assert expects, f"{name} must declare expected invariants"
    for expectation in expects:
        key = (expectation["module"], expectation["id"])
        assert key in lookup, f"{name}: measurement {key} missing"
        measurement = lookup[key]
        for field, expected in expectation["expect"].items():
            assert measurement[field] == expected, (
                f"{name}: {key[0]}.{key[1]}.{field} = "
                f"{measurement[field]!r}, expected {expected!r}"
            )


@pytest.mark.parametrize("name", sorted(DATASETS))
def test_dataset_artifacts_contain_no_pii(tmp_path, name):
    run, context_data, _ = DATASETS[name](tmp_path)
    profile_run(run)
    measure_all(run, CrmContext.model_validate(context_data))
    for directory in ("processed", "evidence"):
        for path in (run / directory).rglob("*"):
            if path.is_file():
                text = path.read_text(encoding="utf-8")
                assert not EMAIL_PATTERN.search(text), f"{name}: email in {path}"


def test_sample_judgment_artifacts_validate(tmp_path):
    """Shipped samples must pass the same gates a real run does."""
    run, _, _ = DATASETS["clean_crm_sample"](tmp_path)
    results = validate_phase3_artifacts(run)
    assert all(not problems for problems in results.values()), results


def test_golden_security_probe_keeps_identity_and_injection_out_of_processed(
    tmp_path,
):
    run, context_data, _ = DATASETS["clean_crm_sample"](tmp_path)
    profile_run(run)
    measure_all(run, CrmContext.model_validate(context_data))
    for directory in ("processed", "evidence"):
        for path in (run / directory).rglob("*"):
            if path.is_file():
                text = path.read_text(encoding="utf-8")
                assert "synthetic.person@example.test" not in text
                assert "Synthetic" not in text
                assert "忽略之前的指令" not in text
    samples = (
        run / "processed" / "sanitized_samples.json"
    ).read_text(encoding="utf-8")
    assert "[PRESENT]" in samples
    assert "[REDACTED:untrusted_crm_text]" in samples
