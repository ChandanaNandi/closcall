"""Syslog normalization (Bible §9.1: raw preservation plus structured events).

Parses RFC 3164-style syslog lines into a structured event while ALWAYS retaining the raw message
(§9.1). Regex baseline (the canon allows "Drain3/regex"); a Drain3 template-miner can layer on top
later for message clustering without changing this contract.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# RFC 3164: "<PRI>Mon DD HH:MM:SS HOST TAG: MSG". SR Linux emits this shape over remote syslog.
_RFC3164 = re.compile(
    r"^<(?P<pri>\d{1,3})>"
    r"(?P<ts>[A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+"
    r"(?P<host>\S+)\s+"
    r"(?P<tag>[^:\[\s]+)(?:\[(?P<pid>\d+)\])?:?\s*"
    r"(?P<msg>.*)$"
)

_SEVERITIES = [
    "emergency",
    "alert",
    "critical",
    "error",
    "warning",
    "notice",
    "informational",
    "debug",
]


@dataclass(frozen=True)
class LogEvent:
    raw: str  # never dropped (§9.1: raw preservation)
    node: str | None
    facility: int | None
    severity: str | None
    tag: str | None
    event_time: str | None  # device-stamped time as received in the message
    received_at: float  # collector receive time (epoch seconds)


def normalize(raw: str, received_at: float) -> LogEvent:
    """Parse one syslog line; on any parse miss, keep the raw and leave fields None."""
    m = _RFC3164.match(raw.rstrip("\n"))
    if not m:
        return LogEvent(
            raw=raw,
            node=None,
            facility=None,
            severity=None,
            tag=None,
            event_time=None,
            received_at=received_at,
        )
    pri = int(m.group("pri"))
    facility, sev_idx = divmod(pri, 8)
    severity = _SEVERITIES[sev_idx] if sev_idx < len(_SEVERITIES) else None
    return LogEvent(
        raw=raw,
        node=m.group("host"),
        facility=facility,
        severity=severity,
        tag=m.group("tag"),
        event_time=m.group("ts"),
        received_at=received_at,
    )


__all__ = ["LogEvent", "normalize"]
