"""Renderer determinism (acceptance A04) and PKI-exclusion tests."""

from pathlib import Path

from closcall.domain.fabric import load_fabric
from closcall.domain.render import render_all

FABRIC = Path(__file__).resolve().parents[2] / "lab" / "fabric.yaml"


def test_render_is_byte_identical_across_runs(tmp_path: Path) -> None:
    a = render_all(load_fabric(FABRIC), tmp_path / "a")
    b = render_all(load_fabric(FABRIC), tmp_path / "b")
    assert a == b, "render produced different file hashes across two runs (A04 violation)"
    # And the actual file bytes match, not just the reported hashes.
    for name in a:
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes()


def test_manifest_excludes_pki(tmp_path: Path) -> None:
    files = render_all(load_fabric(FABRIC), tmp_path / "out")
    # No cert/key material is hashed into the determinism manifest (would carry random serials).
    assert not any(name.endswith((".pem", ".crt", ".key")) for name in files)


def test_expected_artifacts_present(tmp_path: Path) -> None:
    files = render_all(load_fabric(FABRIC), tmp_path / "out")
    for expected in (
        "spine1.cli",
        "leaf1.cli",
        "topology-srl.clab.yml",
        "topology.json",
        "ipam.md",
    ):
        assert expected in files
