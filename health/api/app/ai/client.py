"""One Anthropic client for the process. Credentials come from the environment
(ANTHROPIC_API_KEY, or an `ant auth login` profile) so nothing is passed here."""
from __future__ import annotations

import anthropic

_client: anthropic.Anthropic | None = None


def client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(max_retries=3)
    return _client
