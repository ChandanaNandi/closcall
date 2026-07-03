# B09 ECMP Distribution — Pre-Registration (FROZEN before execution)

Status: frozen 2026-07-03, before any flow was run. The declared tolerance is immutable; an
out-of-band result is a recorded finding about ECMP behavior, never a license to widen the band
(Bible §7.3: distribution tolerance declared before the test).

## Hash-input evidence (from the pinned SR Linux 25.3.3 image, live state)
`info from state system load-balancing hash-options` on a fabric leaf reports, by default:
`source-address true, destination-address true, protocol true, source-port true,
destination-port true`. The device hashes on L4 ports by default, so varying the UDP source port
from a single host pair (fixed src/dst IP + protocol) spreads flows across the two ECMP next hops.

## Design
- Path under test: leaf1 -> host4 subnet; leaf1 has exactly 2 ECMP next hops (spine1 via
  ethernet-1/1, spine2 via ethernet-1/2), confirmed in B06.
- Flows: host1 (172.16.1.10) -> host4 (172.16.4.10), 256 distinct five-tuples, varying UDP source
  port over 256 values, fixed small burst per flow.
- Measurement: delta of leaf1 egress packet counters on ethernet-1/1.0 vs ethernet-1/2.0 (snapshot
  before/after). Per-path share = uplink delta / total delta.

## Flow-count justification
256 flows over 2 equal paths: Binomial(256, 0.5), expected 50%, std dev = sqrt(256*0.25) ≈ 8 flows
≈ 3.1%. "Hundreds" per the canon; large enough that hash variance is ~±3% (1σ).

## Declared tolerance (IMMUTABLE)
PASS iff each path carries between 35% and 65% of measured egress packets. The 35-65% band is
≈ ±4.8σ around 50% (false-fail probability < 0.01%), while any failure mode (IP-only hash or
single-path forwarding -> ~100/0) falls far outside and fails decisively.

## Guardrails
- Memory (§17): snapshot VM memory at flow-test peak; halt and escalate if it crowds the 16 GiB VM
  rather than shrinking the flow count.
- Clean state: run on a freshly deployed, converged fabric.
