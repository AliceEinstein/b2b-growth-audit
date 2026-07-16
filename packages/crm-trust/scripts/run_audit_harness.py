"""Run the CRM Audit artifact-driven BYO Agent harness.

Examples:
    python -m scripts.run_audit_harness init --run examples/mock_midmarket_abm_sales
    python -m scripts.run_audit_harness advance --run outputs/run_x
    python -m scripts.run_audit_harness status --run outputs/run_x
    python -m scripts.run_audit_harness validate --run outputs/run_x --stage findings_validation
"""
from harness.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
