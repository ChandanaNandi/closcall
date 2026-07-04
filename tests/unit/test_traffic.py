"""§8.1 traffic generator — deterministic flow planning + aggregation. Pure/offline."""

from __future__ import annotations

from closcall.traffic.generator import (
    Flow,
    FlowResult,
    TrafficProfile,
    plan_flows,
    run_traffic,
)

HOSTS = ["host1", "host2", "host3", "host4"]


def _profile(pattern: str, **over) -> TrafficProfile:  # type: ignore[no-untyped-def]
    base = dict(
        name="t",
        pattern=pattern,
        streams_per_flow=4,
        target_bitrate_bps=100_000_000,
        duration_s=10,
        seed=1337,
    )
    base.update(over)
    return TrafficProfile(**base)  # type: ignore[arg-type]


def test_all_to_all_plans_every_ordered_pair() -> None:
    flows = plan_flows(_profile("all_to_all"), HOSTS)
    assert len(flows) == 4 * 3  # N*(N-1) directed pairs
    assert all(f.src != f.dst for f in flows)
    assert all(f.streams == 4 for f in flows)


def test_incast_plans_all_senders_to_one_target() -> None:
    flows = plan_flows(_profile("incast", incast_target="host1", streams_per_flow=8), HOSTS)
    assert len(flows) == 3  # host2/3/4 -> host1
    assert {f.dst for f in flows} == {"host1"}
    assert all(f.streams == 8 for f in flows)


def test_flow_plan_is_deterministic_given_seed() -> None:
    a = plan_flows(_profile("all_to_all", seed=42), HOSTS)
    b = plan_flows(_profile("all_to_all", seed=42), HOSTS)
    assert a == b  # reproducible five-tuple assignment (§8.1)
    diff = plan_flows(_profile("all_to_all", seed=99), HOSTS)
    assert diff[0].base_port != a[0].base_port  # seed changes the port assignment


def test_run_aggregates_offered_vs_observed_and_completion() -> None:
    def fake_runner(flow: Flow, profile: TrafficProfile) -> FlowResult:
        # observe 80% of offered, a little loss, complete
        return FlowResult(
            flow,
            observed_bps=profile.target_bitrate_bps * 0.8,
            retransmits=5,
            rtt_ms=2.0,
            completed=True,
        )

    profile = _profile("all_to_all")
    res = run_traffic(profile, HOSTS, fake_runner)
    n = 12
    assert res.flows == n and res.completed == n
    assert res.requested_bps == profile.target_bitrate_bps * n
    assert abs(res.observed_bps - profile.target_bitrate_bps * 0.8 * n) < 1
    assert res.retransmits == 5 * n and res.rtt_ms_mean == 2.0


def test_incomplete_flows_counted() -> None:
    def flaky(flow: Flow, profile: TrafficProfile) -> FlowResult:
        return FlowResult(flow, observed_bps=0.0, retransmits=0, rtt_ms=0.0, completed=False)

    res = run_traffic(_profile("incast", incast_target="host1"), HOSTS, flaky)
    assert res.completed == 0 and res.observed_bps == 0.0
