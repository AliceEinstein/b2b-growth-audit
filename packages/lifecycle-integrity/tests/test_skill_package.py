from __future__ import annotations

import re

from scripts.install_skill import SKILL_NAME, SKILL_SRC
from core.lifecycle_final_gate import FINAL_DELIVERABLES
from scripts.check_hubspot_connection import (
    CORE_REQUIRED_SCOPES,
    FULL_DIAGNOSTIC_SCOPE,
    INTENT_SCOPES,
)


def test_installer_targets_the_lifecycle_skill_package():
    assert SKILL_NAME == "hubspot-lifecycle-integrity-audit"
    assert (SKILL_SRC / "SKILL.md").exists()
    assert (SKILL_SRC / "agents" / "openai.yaml").exists()


def test_skill_tells_global_installs_where_commands_must_run():
    text = (SKILL_SRC / "SKILL.md").read_text(encoding="utf-8")
    assert "Every `python -m scripts.*` command" in text
    assert "Claude symlink install" in text
    assert "sibling `package/` directory" in text


def test_public_artifact_contract_matches_final_gate():
    skill = (SKILL_SRC / "SKILL.md").read_text(encoding="utf-8")
    contract = (SKILL_SRC / "output_contract.md").read_text(encoding="utf-8")
    for filename in FINAL_DELIVERABLES:
        assert filename in skill, filename
        assert filename in contract, filename
    assert "final_gate_report.json" in skill
    assert "final_gate_report.json" in contract


def test_permission_checklist_matches_preflight_scope_ids():
    permissions = (SKILL_SRC / "hubspot_scopes.md").read_text(encoding="utf-8")
    expected = (*CORE_REQUIRED_SCOPES, FULL_DIAGNOSTIC_SCOPE, *INTENT_SCOPES)
    required_table = permissions.split("## Full Lifecycle Integrity diagnostic", 1)[
        1
    ].split("The unusual-looking IDs", 1)[0]
    documented = set(re.findall(r"^\| `([^`]+)` \|", required_table, re.MULTILINE))
    assert documented == set(expected)
    assert "Exact HubSpot scope ID" in permissions
