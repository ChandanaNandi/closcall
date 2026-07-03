#!/usr/bin/env bash
# containerlab deploy/destroy via docker-out-of-docker (ADR-003). The Docker socket is granted ONLY
# to this ephemeral (--rm) orchestrator container — never to a lab node, app, workflow, or executor.
set -euo pipefail

# Pinned by digest (docs/toolchain.md). "latest" is forbidden.
CLAB="ghcr.io/srl-labs/clab@sha256:e48396f2245239216fc4a63c1bb5553425930f0beb1aac3e4c2dc3fda57da75f"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
ACTION="${1:?usage: clab.sh <deploy|destroy> [topology]}"
TOPO="${2:-topology-srl.clab.yml}"

docker run --rm --privileged --network host \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /var/run/netns:/var/run/netns \
  -v /var/lib/docker/containers:/var/lib/docker/containers \
  --pid=host \
  -v "$REPO":"$REPO" -w "$REPO/lab/generated" \
  "$CLAB" containerlab "$ACTION" -t "$TOPO"
