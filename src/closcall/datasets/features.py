"""§9.2 causal-feature builder (Bible §9.2, §10.3; Contracts §9.2).

Turns a §9.1 raw-telemetry window into one model-ready feature example, conforming to the frozen
`CAUSAL_FEATURE_COLUMNS`. Strictly causal (§10.3): for decision time `as_of_at`, only samples with
`event_time in [as_of_at - W, as_of_at]` are read — nothing after `as_of_at`, and none of the
`FORBIDDEN_FEATURE_COLUMNS` (t_clear, t_settled, incident_duration, ground truth, label, scenario
key, split answer) may enter a feature. Ground truth is never here; it is joined only at scoring.

Counters (octets, error/discard packets) become per-second rates via endpoint deltas over the
window; oper-state contributes to the missingness mask. `util_ratio` normalizes octet throughput by
a nominal lab link capacity (fidelity note: the clab veths enforce no real capacity, so util_ratio
is a normalized-throughput signal, not hardware utilization — the fault signal is in the rates).

`missingness_mask` (bit set == channel MISSING in the window, §9.2): bit0 util/octets, bit1 error,
bit2 discard, bit3 oper-state.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass

from closcall.datasets.schemas import (
    CAUSAL_FEATURE_COLUMNS,
    FORBIDDEN_FEATURE_COLUMNS,
    schema_hash,
)

NOMINAL_CAPACITY_BPS = 1e9  # lab nominal (1 Gbps) for util normalization; documented fidelity limit

# Pinned preprocessing config -> preprocessor_hash. Any change to how features are computed must
# change this dict (and thus the hash), creating a new benchmark version (§16).
_PREPROCESSOR = {
    "code": "gate9-causal-features-v1",
    "capacity_bps": NOMINAL_CAPACITY_BPS,
    "rate_method": "endpoint-delta",
    "channels": ["util_ratio", "error_rate", "discard_rate", "oper_state"],
}


@dataclass(frozen=True)
class RawSample:
    """One §9.1 telemetry sample reduced to what the feature stage reads."""

    t: float  # event_time as epoch seconds
    metric: str
    value: float


@dataclass(frozen=True)
class FeatureMeta:
    """Non-computed §9.2 columns supplied by the corpus (metadata, never features)."""

    example_id: str
    split: str
    incident_runtime_id: str
    node: str
    interface: str
    window_start: float
    window_end: float
    as_of_at: float


def preprocessor_hash(w_seconds: float) -> str:
    payload = {**_PREPROCESSOR, "w_seconds": w_seconds}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _rate(samples: list[RawSample]) -> tuple[float, bool]:
    """Per-second rate from endpoint delta over the window; 2nd value = present-enough-for-rate."""
    if len(samples) < 2:
        return 0.0, False
    pts = sorted(samples, key=lambda s: s.t)
    dt = pts[-1].t - pts[0].t
    if dt <= 0:
        return 0.0, True
    dv = pts[-1].value - pts[0].value
    if dv < 0:  # counter reset within window -> treat as no observed increase
        dv = 0.0
    return dv / dt, True


def causal_features(
    samples: list[RawSample],
    *,
    as_of_at: float,
    w_seconds: float,
    capacity_bps: float = NOMINAL_CAPACITY_BPS,
) -> dict[str, float | int]:
    """Compute numeric §9.2 features + missingness/age from the causal window [as_of_at-W, t]."""
    lo = as_of_at - w_seconds
    win = [s for s in samples if lo <= s.t <= as_of_at]  # causal: never read past as_of_at
    by: dict[str, list[RawSample]] = defaultdict(list)
    for s in win:
        by[s.metric].append(s)

    in_o, p_ino = _rate(by["in_octets"])
    out_o, p_outo = _rate(by["out_octets"])
    in_e, p_ine = _rate(by["in_error_packets"])
    out_e, p_oute = _rate(by["out_error_packets"])
    in_d, p_ind = _rate(by["in_discarded_packets"])
    out_d, p_outd = _rate(by["out_discarded_packets"])

    octet_bps = 8.0 * max(in_o, out_o)
    util_ratio = min(1.0, max(0.0, octet_bps / capacity_bps))
    error_rate = in_e + out_e
    discard_rate = in_d + out_d

    util_present = p_ino and p_outo
    error_present = p_ine and p_oute
    discard_present = p_ind and p_outd
    oper_present = len(by["oper_state"]) >= 1

    last_t = max((s.t for s in win), default=None)
    sample_age_s = (as_of_at - last_t) if last_t is not None else w_seconds

    # bit set == MISSING (§9.2): bit0 util, bit1 error, bit2 discard, bit3 oper
    missingness_mask = (
        (0 if util_present else 1)
        | (0 if error_present else 1) << 1
        | (0 if discard_present else 1) << 2
        | (0 if oper_present else 1) << 3
    )
    return {
        "util_ratio": util_ratio,
        "error_rate": error_rate,
        "discard_rate": discard_rate,
        "sample_age_s": sample_age_s,
        "missingness_mask": missingness_mask,
    }


def build_feature_row(
    meta: FeatureMeta,
    samples: list[RawSample],
    *,
    capacity_bps: float = NOMINAL_CAPACITY_BPS,
) -> dict[str, object]:
    """Assemble one §9.2 feature row conforming to `CAUSAL_FEATURE_COLUMNS` (leakage-free)."""
    # read span W = the captured window; with as_of_at = window_end this is [window_start, t].
    # (This sizes the causal read only; incident_duration is never emitted as a feature.)
    w_seconds = meta.window_end - meta.window_start
    feats = causal_features(
        samples, as_of_at=meta.as_of_at, w_seconds=w_seconds, capacity_bps=capacity_bps
    )
    row: dict[str, object] = {
        "example_id": meta.example_id,
        "split": meta.split,
        "incident_runtime_id": meta.incident_runtime_id,
        "window_start": meta.window_start,
        "window_end": meta.window_end,
        "as_of_at": meta.as_of_at,
        "node": meta.node,
        "interface": meta.interface,
        **feats,
        "feature_schema_hash": schema_hash(),
        "preprocessor_hash": preprocessor_hash(w_seconds),
    }
    # invariants: exact frozen column set, and no forbidden leakage column ever present
    assert set(row) == set(CAUSAL_FEATURE_COLUMNS), set(row) ^ set(CAUSAL_FEATURE_COLUMNS)
    assert not (set(row) & FORBIDDEN_FEATURE_COLUMNS)
    return row


__all__ = [
    "NOMINAL_CAPACITY_BPS",
    "FeatureMeta",
    "RawSample",
    "build_feature_row",
    "causal_features",
    "preprocessor_hash",
]
