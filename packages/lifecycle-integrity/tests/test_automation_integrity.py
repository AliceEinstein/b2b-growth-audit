from __future__ import annotations

import json
from pathlib import Path

import httpx

from connectors.hubspot.client import HubSpotClient
from connectors.hubspot.fetch_automation import (
    read_workflow_details,
    fetch_snapshot,
)
from connectors.hubspot.rate_limit import RateLimitPolicy
from core.automation_integrity import build_automation_integrity_artifacts
from core.lifecycle_validators import validate_root_cause_assessments
from lifecycle_test_support import build_lifecycle_run, write_judgment_artifacts


TOKEN = "pat-" + "na1-00000000-0000-0000-000000000000"


def _client(handler) -> HubSpotClient:
    return HubSpotClient(
        TOKEN,
        transport=httpx.MockTransport(handler),
        policy=RateLimitPolicy(max_retries=0, base_delay=0),
        sleep=lambda _: None,
    )


def test_automation_fetches_paginated_inventory_details_and_performance(tmp_path):
    def handler(request):
        path = request.url.path
        if path == "/automation/v4/flows":
            if request.url.params.get("after"):
                return httpx.Response(200, json={"results": [{"id": "3"}]})
            return httpx.Response(
                200,
                json={
                    "results": [{"id": "1"}, {"id": "2"}],
                    "paging": {"next": {"after": "2"}},
                },
            )
        if path == "/automation/v4/flows/batch/read":
            ids = [row["flowId"] for row in json.loads(request.content)["inputs"]]
            return httpx.Response(
                200,
                json={
                    "results": [
                        {"id": flow_id, "name": f"Workflow {flow_id}", "isEnabled": True}
                        for flow_id in ids
                    ]
                },
            )
        if path.startswith("/automation/v3/performance/workflow/"):
            return httpx.Response(
                200,
                json=[{"series": "ENROLLED", "frequency": 4}],
            )
        raise AssertionError(path)

    coverage = fetch_snapshot(
        _client(handler),
        tmp_path / "raw",
        days=30,
        completed_at="2026-07-15T00:00:00+00:00",
    )
    assert coverage["status"] == "full"
    assert coverage["workflow_inventory_count"] == 3
    assert coverage["workflow_detail_count"] == 3
    assert coverage["performance_workflow_count"] == 3
    assert len(json.loads((tmp_path / "raw" / "automation" / "workflows.json").read_text())) == 3


def test_automation_detail_batch_failure_falls_back_to_individual_reads():
    def handler(request):
        if request.url.path == "/automation/v4/flows/batch/read":
            return httpx.Response(403)
        if request.url.path.startswith("/automation/v4/flows/"):
            return httpx.Response(
                200,
                json={"id": request.url.path.rsplit("/", 1)[-1], "name": "Fallback"},
            )
        raise AssertionError(request.url.path)

    details, failures = read_workflow_details(
        _client(handler),
        [{"id": "11"}, {"id": "12"}],
    )
    assert {row["id"] for row in details} == {"11", "12"}
    assert failures == []


def test_automation_scope_failure_is_explicit_and_non_fatal(tmp_path):
    def handler(request):
        return httpx.Response(403)

    coverage = fetch_snapshot(
        _client(handler),
        tmp_path / "raw",
        days=None,
        completed_at="2026-07-15T00:00:00+00:00",
    )
    assert coverage["status"] == "unavailable"
    assert coverage["workflow_inventory_count"] == 0
    assert json.loads((tmp_path / "raw" / "automation" / "workflows.json").read_text()) == []


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def test_automation_integrity_emits_sanitized_checks_and_measurement_links(tmp_path):
    run_dir = tmp_path / "run"
    raw = run_dir / "raw"
    raw.mkdir(parents=True)
    for object_type, definitions in {
        "contacts": [
            {"name": "hubspot_owner_id", "label": "Contact owner", "hubspotDefined": True},
            {"name": "lead_score", "label": "Lead score", "hubspotDefined": True},
        ],
        "companies": [],
        "deals": [],
    }.items():
        _write_json(raw / f"properties_{object_type}.json", definitions)
    (raw / "contacts.jsonl").write_text(
        json.dumps({"id": "1", "properties": {"lead_score": "75"}}) + "\n",
        encoding="utf-8",
    )
    _write_json(raw / "companies.jsonl", [])
    _write_json(raw / "deals.jsonl", [])
    _write_json(raw / "owners.json", [{"id": "101"}, {"id": "102"}, {"id": "103"}])
    _write_json(raw / "pipelines.json", [])
    _write_json(
        raw / "automation" / "workflows.json",
        [
            {
                "id": "1",
                "name": "<script>Disabled owner guard</script>",
                "isEnabled": False,
                "actions": [
                    {
                        "type": "PROPERTY_SET",
                        "fields": {"hubspot_owner_id": "101"},
                        "propertyName": "missing_property",
                    }
                ],
            },
            {
                "id": "2",
                "name": "Active owner guard",
                "isEnabled": True,
                "actions": [
                    {"type": "PROPERTY_SET", "fields": {"hubspot_owner_id": "102"}}
                ],
            },
            {
                "id": "3",
                "name": "Second active owner guard",
                "isEnabled": True,
                "actions": [
                    {
                        "type": "PROPERTY_SET",
                        "inputFields": {"hubspot_owner_id": "103"},
                    }
                ],
            },
        ],
    )
    _write_json(raw / "automation" / "workflow_performance.json", [])
    _write_json(
        run_dir / "processed" / "lifecycle_integrity_measurements.json",
        {
            "measurements": [
                {
                    "id": "owner_handoff_missing_owner",
                    "field_name": "hubspot_owner_id",
                    "integrity_dimension": "handoff_integrity",
                    "available": True,
                    "affected_records": 2,
                    "denominator": 10,
                }
            ]
        },
    )
    _write_json(
        run_dir / "manifest.json",
        {
            "status": "completed",
            "automation": {
                "status": "full",
                "workflow_inventory_count": 3,
                "performance_window": {"label": "30 days"},
                "limitations": [],
            },
        },
    )

    artifact = build_automation_integrity_artifacts(run_dir)
    issue_types = {row["issue_type"] for row in artifact["checks"]}
    assert {"relevant_workflow_disabled", "conflicting_active_writers"}.issubset(issue_types)
    assert "workflow_reference_not_in_snapshot_schema" in issue_types
    assert "score_output_not_referenced_by_workflow" in issue_types
    link = artifact["root_cause_links"][0]
    assert link["measurement_id"] == "owner_handoff_missing_owner"
    assert link["workflow_aliases"]
    evidence = (run_dir / "automation_evidence.csv").read_text(encoding="utf-8")
    assert "<script>" not in evidence
    assert "[CRM_FIELD_VALUE:UNTRUSTED_DATA_ONLY]" in evidence


def test_root_cause_cross_references_are_deterministically_checked(tmp_path):
    run_dir, _ = build_lifecycle_run(tmp_path, "broken_association_sample")
    write_judgment_artifacts(run_dir, "deals_without_company")
    build_automation_integrity_artifacts(run_dir)
    path = run_dir / "agent_workspace" / "root_cause" / "automation_root_cause_agent.json"
    path.write_text(
        json.dumps(
            {
                "role": "automation_root_cause_agent",
                "assessments": [
                    {
                        "finding_id": "deals_without_company",
                        "configuration_status": "control_absent",
                        "causal_status": "possible",
                        "confidence_score": 30,
                        "workflow_aliases": ["WF-999"],
                        "score_fields": ["not_a_score_field"],
                        "evidence_refs": [
                            "automation_evidence.csv#measurement_id=missing"
                        ],
                        "limitations": [],
                        "recommendation_category": "review_configuration",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    problems = validate_root_cause_assessments(run_dir)
    assert any("unknown workflow aliases" in problem for problem in problems)
    assert any("unknown score fields" in problem for problem in problems)
    assert any("measurement does not exist" in problem for problem in problems)
