"""Token loading and masking.

The full token must never be printed, logged, or written to any artifact.
"""
from __future__ import annotations

import os
import re

from dotenv import load_dotenv

ENV_VAR = "HUBSPOT_PRIVATE_APP_TOKEN"

# HubSpot private app tokens look like: pat-na1-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
_TOKEN_SHAPE = re.compile(r"^pat-[a-z]{2,4}\d?-[0-9a-f-]{16,}$", re.IGNORECASE)


class TokenError(RuntimeError):
    """Raised when the HubSpot token is missing or unusable."""


def load_token(dotenv_path: str | None = None) -> str:
    """Load the private app token from the environment / .env file."""
    load_dotenv(dotenv_path=dotenv_path, override=False)
    token = os.environ.get(ENV_VAR, "").strip()
    if not token:
        raise TokenError(
            f"{ENV_VAR} is not set. Copy .env.example to .env and add your "
            "HubSpot Private App token (Settings → Integrations → Private Apps)."
        )
    return token


def token_looks_valid(token: str) -> bool:
    return bool(_TOKEN_SHAPE.match(token))


def mask_token(token: str) -> str:
    """Display-safe form of the token. Never show more than the prefix."""
    return token[:8] + "…" if len(token) > 8 else "…"
