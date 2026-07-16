from __future__ import annotations

from scripts.install_skill import SKILL_NAME, SKILL_SRC


def test_installer_targets_the_lifecycle_skill_package():
    assert SKILL_NAME == "hubspot-lifecycle-integrity-audit"
    assert (SKILL_SRC / "SKILL.md").exists()
    assert (SKILL_SRC / "agents" / "openai.yaml").exists()
