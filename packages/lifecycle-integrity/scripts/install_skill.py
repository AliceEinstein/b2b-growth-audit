"""Install the audit skill for your coding agent.

Codex and Gemini CLI pick up AGENTS.md / GEMINI.md automatically when you
work inside this repository — no installation needed. Claude Code can
additionally register the skill globally (invocable from any directory)
by linking it into ~/.claude/skills.

Usage:
    python -m scripts.install_skill --agent claude          # symlink (default)
    python -m scripts.install_skill --agent claude --copy
    python -m scripts.install_skill --agent codex
    python -m scripts.install_skill --agent gemini
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL_NAME = "hubspot-lifecycle-integrity-audit"
SKILL_SRC = REPO_ROOT / "skills" / SKILL_NAME


def _copy_ignore(_directory: str, names: list[str]) -> set[str]:
    """Keep a global copy runnable without copying local secrets or outputs."""
    excluded = {
        ".env",
        ".env.local",
        ".envrc",
        ".git",
        ".pytest_cache",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "outputs",
    }
    return {
        name
        for name in names
        if name in excluded
        or (name.startswith(".env.") and name != ".env.example")
    }


def install_claude(copy: bool) -> int:
    target_dir = Path.home() / ".claude" / "skills"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / SKILL_NAME

    if target.is_symlink() or target.exists():
        print(f"Already installed at {target} — remove it first to reinstall.")
        return 1

    if copy:
        # Claude discovers SKILL.md at the skill root, while the audit itself
        # needs the package runtime, role contracts, and validators. Keep both
        # in the copied install so --copy is a real snapshot, not a discovery-
        # only markdown bundle.
        shutil.copytree(SKILL_SRC, target)
        shutil.copytree(REPO_ROOT, target / "package", ignore=_copy_ignore)
        print(f"Copied skill and executable package snapshot to {target}")
        print(
            "This snapshot will not update when the repository changes. Run "
            f"from {target / 'package'} and provide HUBSPOT_PRIVATE_APP_TOKEN "
            "through that package's local .env or your environment."
        )
    else:
        target.symlink_to(SKILL_SRC, target_is_directory=True)
        print(f"Symlinked {target} -> {SKILL_SRC}")

    print(
        "\nDone. In Claude Code, the skill is now discoverable as "
        f"'{SKILL_NAME}'.\nScripts run from the package root "
        f"({target / 'package' if copy else REPO_ROOT}), where the package's "
        "pyproject.toml and local .env live."
    )
    return 0


def explain_repo_native(agent: str, context_file: str) -> int:
    print(
        f"No installation needed for {agent}: it reads {context_file} "
        "automatically when you work inside this repository.\n\n"
        f"    cd {REPO_ROOT}\n"
        f"    # start {agent} here and ask it to run the lifecycle integrity audit\n\n"
        "The context file routes it to AGENTS.md and "
        f"skills/{SKILL_NAME}/SKILL.md."
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--agent", choices=["claude", "codex", "gemini"], required=True
    )
    parser.add_argument("--copy", action="store_true", help="copy instead of symlink")
    args = parser.parse_args()

    if args.agent == "claude":
        return install_claude(args.copy)
    if args.agent == "codex":
        return explain_repo_native("Codex", "AGENTS.md")
    return explain_repo_native("Gemini CLI", "GEMINI.md")


if __name__ == "__main__":
    raise SystemExit(main())
