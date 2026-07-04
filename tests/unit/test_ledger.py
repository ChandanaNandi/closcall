"""Tests for the durable chaos ledger + reconciliation (Bible §8.3)."""

from pathlib import Path

from closcall.chaos.ledger import Ledger, Phase, now_record


def _rec(led: Ledger, iid: str, phase: Phase) -> None:
    led.append(
        now_record(
            iid,
            "impaired_link",
            phase,
            {"node": "leaf1", "interface": "ethernet-1/1"},
            {"kind": "sh", "cmd": "tc qdisc del dev e1-1 root"},
        )
    )


def test_append_and_read(tmp_path: Path) -> None:
    led = Ledger(tmp_path / "l.jsonl")
    _rec(led, "a", Phase.PLANNED)
    recs = led.records()
    assert len(recs) == 1
    assert recs[0].simulated is True  # §2.12
    assert recs[0].cleanup["cmd"].startswith("tc qdisc del")


def test_outstanding_flags_unreconciled(tmp_path: Path) -> None:
    led = Ledger(tmp_path / "l.jsonl")
    # 'a' left ACTIVE (cleanup owed); 'b' fully CLEARED.
    _rec(led, "a", Phase.PLANNED)
    _rec(led, "a", Phase.INJECTING)
    _rec(led, "a", Phase.ACTIVE)
    _rec(led, "b", Phase.PLANNED)
    _rec(led, "b", Phase.CLEARED)
    out = led.outstanding()
    assert [r.injection_id for r in out] == ["a"]
    assert out[0].phase == Phase.ACTIVE


def test_cleared_then_nothing_outstanding(tmp_path: Path) -> None:
    led = Ledger(tmp_path / "l.jsonl")
    for p in (Phase.PLANNED, Phase.INJECTING, Phase.ACTIVE, Phase.CLEARING, Phase.CLEARED):
        _rec(led, "a", p)
    assert led.outstanding() == []


def test_latest_phase_per_id_wins(tmp_path: Path) -> None:
    led = Ledger(tmp_path / "l.jsonl")
    _rec(led, "a", Phase.ACTIVE)
    _rec(led, "a", Phase.CLEARED)
    assert led.outstanding() == []
