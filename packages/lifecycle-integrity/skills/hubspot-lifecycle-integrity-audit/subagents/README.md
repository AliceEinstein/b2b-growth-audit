# Lifecycle audit roles

The orchestrator runs these roles on processed artifacts. Roles do not chat
freely and do not call HubSpot. Each role writes the structured artifact named
in its instruction file, with evidence references, assumptions, limitations,
and confidence.

Run hypothesis roles after the Journey Evidence Store exists. Run integrity
roles only after the Journey Pattern Registry is adjudicated. Run reviewers
before reports. The final report role is last and must pass the safety gate.
