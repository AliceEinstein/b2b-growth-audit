"""Generate the synthetic lifecycle audit portals."""
from __future__ import annotations

from pathlib import Path

from core.audit_logger import AuditLog
from core.automation_integrity import build_automation_integrity_artifacts
from core.journey_evidence import build_journey_evidence_store
from core.lifecycle_agent_tasks import write_agent_task_manifest
from core.lifecycle_rules import measure_lifecycle_integrity
from core.lifecycle_synthetic_datasets import LIFECYCLE_DATASETS, write_expectations
from core.profiler import profile_run


def main() -> int:
    root = Path(__file__).resolve().parents[1] / "examples" / "lifecycle"
    root.mkdir(parents=True, exist_ok=True)
    for name, builder in LIFECYCLE_DATASETS.items():
        run_dir, expectations = builder(root)
        profile_run(run_dir)
        build_journey_evidence_store(run_dir)
        measure_lifecycle_integrity(run_dir)
        build_automation_integrity_artifacts(run_dir)
        write_agent_task_manifest(run_dir, portable=True)
        AuditLog({"synthetic_dataset": name}).write(run_dir / "audit_log.json")
        write_expectations(run_dir, expectations)
        print(f"generated {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
