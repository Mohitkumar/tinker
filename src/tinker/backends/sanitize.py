"""Data sanitization for log content before LLM submission.

Strips patterns that look like credentials or prompt injections from any
external data (log lines, metric labels, trace attributes) before it is
included in a prompt or returned from an MCP tool.
"""

from __future__ import annotations

import re

# Patterns that look like prompt injection or credential leakage
_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+previous\s+instructions", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+", re.IGNORECASE),
    re.compile(r"system\s+prompt", re.IGNORECASE),
    re.compile(r"AKIA[A-Z0-9]{16}"),  # AWS access key
    re.compile(r"sk-ant-[A-Za-z0-9\-]+"),  # Anthropic API key
    re.compile(r"xox[bpa]-[A-Za-z0-9\-]+"),  # Slack tokens
    re.compile(r"ghp_[A-Za-z0-9]{36}"),  # GitHub tokens
]


def sanitize_log_content(content: str) -> str:
    """Remove credential and prompt-injection patterns from *content*.

    Call this on any external data before including it in an LLM prompt
    or returning it from an MCP tool.
    """
    for pattern in _INJECTION_PATTERNS:
        content = pattern.sub("[REDACTED]", content)
    return content
