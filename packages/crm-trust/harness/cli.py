"""CLI for the artifact-driven BYO Agent harness."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Optional

from core.client_config import FIELD_OVERRIDES_PATH, ClientConfigError, install_field_overrides

from .engine import advance, ensure_run, status, validate
from .task_packets import read_task


def _dump(value: Any, as_json: bool) -> None:
    if as_json:
        print(json.dumps(value, ensure_ascii=False, indent=2))
        return
    if isinstance(value, dict) and "stages" in value:
        print("CRM Audit harness: " + value.get("mode", "byo_agent"))
        for stage, state in value["stages"].items():
            marker = "✅" if state["status"] in {"passed", "skipped"} else "⏳" if state["status"] == "ready" else "❌" if state["status"] == "failed" else "·"
            print(marker + " " + stage + ": " + state["status"])
            if state.get("task_file"):
                print("   task: " + state["task_file"])
            if state.get("last_error"):
                print("   error: " + state["last_error"])
        return
    print(json.dumps(value, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the CRM Audit in BYO Agent mode without a model API key."
    )
    parser.add_argument("command", choices=["init", "run", "advance", "status", "validate", "task"])
    parser.add_argument("--run", type=Path, required=True, help="Completed snapshot run directory")
    parser.add_argument("--stage", default=None, help="Stage id for validate/task")
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument(
        "--field-overrides",
        type=Path,
        default=None,
        help=(
            "init only: owner-confirmed canonical fields (the lifecycle audit's "
            "confirmed field_overrides.yaml). Schema discovery and every later stage "
            "re-run with them."
        ),
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.field_overrides is not None and args.command != "init":
        raise SystemExit("--field-overrides is only accepted with init")
    if args.command in {"init", "run", "advance"}:
        if args.command == "init":
            if args.field_overrides is not None:
                try:
                    install_field_overrides(args.run, args.field_overrides)
                except ClientConfigError as exc:
                    print("Client config rejected: " + str(exc))
                    return 1
                print("Owner-confirmed fields installed: " + str(Path(args.run) / FIELD_OVERRIDES_PATH))
            ensure_run(args.run)
        result = advance(args.run)
        if args.as_json:
            _dump({"advance": result, "status": status(args.run)}, True)
        else:
            print("BYO Agent harness advanced.")
            if result["ready_tasks"]:
                print("Agent tasks ready:")
                for task in result["ready_tasks"]:
                    print("- " + str(Path(args.run) / "harness" / "tasks" / (task + ".md")))
            if result["failed"]:
                print("Failed stages: " + ", ".join(result["failed"]))
            if not result["ready_tasks"] and not result["failed"]:
                print("No agent task is waiting; run status to inspect completion.")
        return 0
    if args.command == "status":
        _dump(status(args.run), args.as_json)
        return 0
    if args.command == "task":
        if not args.stage:
            raise SystemExit("--stage is required for task")
        _dump(read_task(args.run, args.stage), True)
        return 0
    if args.command == "validate":
        results = validate(args.run, args.stage)
        _dump(results, args.as_json)
        return 0 if not any(results.values()) else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
