"""Collective-shaped traffic generator (Bible §8.1).

Produces reproducible many-flow bursts resembling collective-communication rhythm (NOT
NCCL/all-reduce validation — just the shape). Flows run host-to-host across the Clos, loading the
leaf uplinks where faults inject, so gray/congestion faults (rate_limited, impaired) finally produce
device-counter signatures and healthy-high-util hard-negatives exist. Each run records offered vs
observed bitrate, flow count, seed, retransmits (loss proxy), RTT, and completion (§8.1).

Flow planning and aggregation are pure/seeded (unit-tested offline); the actual iperf3 execution
is an injected `FlowRunner`, so the real runner (docker exec iperf3 -J) is the only lab-bound part.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

PATTERNS = ("all_to_all", "incast")


@dataclass(frozen=True)
class TrafficProfile:
    name: str
    pattern: str  # "all_to_all" | "incast"
    streams_per_flow: int  # parallel iperf3 streams per host-pair (many-flow shape)
    target_bitrate_bps: int  # offered load per flow
    duration_s: int
    seed: int
    incast_target: str | None = None  # receiver host for the incast pattern
    impaired: bool = False  # False for a healthy hard-negative (high util, no impairment)


@dataclass(frozen=True)
class Flow:
    src: str  # sender host
    dst: str  # receiver host
    streams: int
    base_port: int


@dataclass(frozen=True)
class FlowResult:
    flow: Flow
    observed_bps: float
    retransmits: int  # loss proxy
    rtt_ms: float
    completed: bool


@dataclass(frozen=True)
class TrafficResult:
    profile: str
    seed: int
    requested_bps: int
    observed_bps: float
    flows: int
    completed: int
    retransmits: int
    rtt_ms_mean: float


FlowRunner = Callable[[Flow, TrafficProfile], FlowResult]


def plan_flows(profile: TrafficProfile, hosts: list[str]) -> list[Flow]:
    """Deterministic flow plan from pattern + seed (reproducible five-tuple assignment, §8.1)."""
    ordered = sorted(hosts)  # stable order -> reproducible given the seed
    port = 5200 + (profile.seed % 100)  # seed-derived base port (part of the five-tuple)
    flows: list[Flow] = []
    if profile.pattern == "incast":
        target = profile.incast_target or ordered[0]
        for i, src in enumerate(h for h in ordered if h != target):
            flows.append(Flow(src, target, profile.streams_per_flow, port + i))
    elif profile.pattern == "all_to_all":
        i = 0
        for src in ordered:
            for dst in ordered:
                if src != dst:
                    flows.append(Flow(src, dst, profile.streams_per_flow, port + i))
                    i += 1
    else:
        raise ValueError(f"unknown pattern {profile.pattern!r}")
    return flows


def run_traffic(profile: TrafficProfile, hosts: list[str], runner: FlowRunner) -> TrafficResult:
    """Plan flows, run each through the injected runner, and aggregate the §8.1 record."""
    flows = plan_flows(profile, hosts)
    results = [runner(f, profile) for f in flows]
    completed = [r for r in results if r.completed]
    observed = sum(r.observed_bps for r in results)
    retransmits = sum(r.retransmits for r in results)
    rtts = [r.rtt_ms for r in results if r.rtt_ms > 0]
    return TrafficResult(
        profile=profile.name,
        seed=profile.seed,
        requested_bps=profile.target_bitrate_bps * len(flows),
        observed_bps=observed,
        flows=len(flows),
        completed=len(completed),
        retransmits=retransmits,
        rtt_ms_mean=(sum(rtts) / len(rtts)) if rtts else 0.0,
    )


__all__ = [
    "PATTERNS",
    "Flow",
    "FlowResult",
    "FlowRunner",
    "TrafficProfile",
    "TrafficResult",
    "plan_flows",
    "run_traffic",
]
