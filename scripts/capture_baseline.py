"""Capture a healthy fabric-wide telemetry baseline (Gate 9 localization, pilot decision).

The corpus captured only each incident's TARGET link, so a graph localization example has features
on one node and none elsewhere — which makes localization trivial/leaky. Rather than re-collect (the
pilot chose not to), this captures ONE healthy window per SR-Linux interface endpoint from the idle
fabric, captured EXACTLY like the corpus windows (same §9.1 path, same job pin, same length), to
populate the non-target links in each incident's graph.

Documented fidelity limit: the baseline is a single static healthy snapshot, not the concurrent
fabric state during each incident. Host-side access-link ends have no gnmic telemetry (masked).
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from closcall.datasets.graph import build_topology_graph  # noqa: E402
from closcall.datasets.telemetry_window import capture_window  # noqa: E402
from closcall.domain.fabric import allocate, load_fabric  # noqa: E402

CAMPAIGN_KEY = "healthy-baseline"
WINDOW_S = 25.0
DATA_ROOT = REPO / "data"


def topology_hash() -> str:
    import hashlib

    return hashlib.sha256((REPO / "lab" / "fabric.yaml").read_bytes()).hexdigest()[:16]


def main() -> int:
    topo = allocate(load_fabric("lab/fabric.yaml"))
    graph = build_topology_graph(topo)
    role = {d.id: d.role for d in graph.device_nodes}
    topo_hash = topology_hash()
    end = datetime.now(UTC)
    start = end - timedelta(seconds=WINDOW_S)

    captured = skipped = 0
    for node in graph.interface_nodes:
        if role[node.device] == "host":  # linux hosts export no gnmic telemetry
            skipped += 1
            continue
        iface = node.id.split(":", 1)[1]
        cap = capture_window(
            node=node.device,
            iface_srl=iface,
            window_start=start,
            window_end=end,
            campaign_key=CAMPAIGN_KEY,
            topology_hash=topo_hash,
            incident_id=node.id.replace(":", "-").replace("/", "_"),
            out_root=DATA_ROOT,
        )
        if cap.n_rows > 0:
            captured += 1
        else:
            skipped += 1
    print(
        f"healthy baseline captured: {captured} SR-Linux endpoints ({skipped} skipped/host-masked)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
