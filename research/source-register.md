# ClosCall — Primary Source Register

The implementation records exact versions, commits, and access dates in `docs/toolchain.md`.
This planning register defines the primary sources that support architecture and evaluation choices.

## Network and lab

- RFC 7938, *Use of BGP for Routing in Large-Scale Data Centers*:
  https://datatracker.ietf.org/doc/html/rfc7938
- Containerlab macOS guidance:
  https://containerlab.dev/macos/
- Containerlab management networking:
  https://containerlab.dev/manual/network/
- Containerlab link impairments:
  https://containerlab.dev/manual/impairments/
- Nokia SR Linux ARM64 image:
  https://learn.srlinux.dev/blog/2024/sr-linux-container-image-for-arm64/
- Nokia SR Linux BGP documentation:
  https://documentation.nokia.com/srlinux/
- OpenConfig gNMI specification:
  https://openconfig.net/docs/gnmi/gnmi-specification/
- gNMIc containerlab/Prometheus deployment:
  https://gnmic.openconfig.net/deployments/single-instance/containerlab/prometheus-remote-write-output/

## Telemetry, database, and workflow

- Prometheus metric/label naming:
  https://prometheus.io/docs/practices/naming/
- Prometheus exporter guidance:
  https://prometheus.io/docs/instrumenting/writing_exporters/
- PostgreSQL 16 documentation:
  https://www.postgresql.org/docs/16/
- LangGraph persistence:
  https://docs.langchain.com/oss/python/langgraph/persistence
- LangGraph interrupts/HITL:
  https://docs.langchain.com/oss/python/langgraph/interrupts

## ML and evaluation

- PatchTST:
  https://arxiv.org/abs/2211.14730
- Chronos:
  https://arxiv.org/abs/2403.07815
- GraphSAGE:
  https://arxiv.org/abs/1706.02216
- Graph Attention Networks:
  https://arxiv.org/abs/1710.10903
- REASON:
  https://arxiv.org/abs/2302.01987
- Time-series anomaly benchmark pitfalls:
  https://arxiv.org/abs/2009.13807
- NetCause, graph-temporal counterfactual network RCA:
  https://arxiv.org/abs/2606.13543

## Agent/network troubleshooting evaluation

- NIKA paper:
  https://arxiv.org/abs/2512.16381
- NIKA evolving repository:
  https://github.com/sands-lab/nika
- SADE:
  https://arxiv.org/abs/2605.04530

## Source-use rules

- Paper results describe the paper version, not the latest repository.
- Repository claims pin a commit.
- Tool behavior pins documentation and software release.
- A source is not cited for a stronger claim than it directly supports.
- Secondary summaries may aid discovery but cannot settle a consequential design decision.
