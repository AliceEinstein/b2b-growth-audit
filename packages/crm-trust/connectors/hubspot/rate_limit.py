"""Retry / backoff policy for HubSpot API calls."""
from __future__ import annotations

from dataclasses import dataclass

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


@dataclass
class RateLimitPolicy:
    max_retries: int = 5
    base_delay: float = 1.0
    max_delay: float = 30.0
    # Conservative success-path pacing for a private app. Search has a
    # stricter endpoint-specific limit and is handled separately by the
    # client. Tests can inject a no-op sleep without changing this policy.
    min_interval: float = 0.12
    search_min_interval: float = 0.22

    def delay(self, attempt: int, retry_after: str | None = None) -> float:
        """Delay before the next attempt. Honors Retry-After when present."""
        if retry_after:
            try:
                return min(float(retry_after), self.max_delay)
            except ValueError:
                pass
        return min(self.base_delay * (2**attempt), self.max_delay)
