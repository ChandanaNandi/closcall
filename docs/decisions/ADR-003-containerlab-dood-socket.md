# ADR-003 — containerlab deployment via docker-out-of-docker (Docker socket mount)

Status: proposed
Date: 2026-07-03

## Context

containerlab cannot run on macOS (Darwin is not Linux; it needs netlink/netns — research log R10,
containerlab.dev/macos). On the Docker Desktop runtime (ADR-002), the supported way to run
containerlab is as a container that drives the Docker daemon — "docker-out-of-docker" (dood): the
containerlab container is given the host Docker socket and creates the lab node containers as
siblings in the same DD VM, then wires veth pairs between their network namespaces.

This requires mounting `/var/run/docker.sock` into the containerlab container. Bible §3.3 forbids
mounting the Docker socket into *application* containers, because socket access is effectively root
on the Docker VM — the single highest-privilege capability in this build. containerlab is the lab
*orchestrator*, not an application container, so it is a legitimate exception — but per the same
seriousness applied to ADR-002, the socket mount is recorded and bounded here rather than waved
through.

**Spike evidence (2026-07-03), containerlab 0.77.0 arm64
`ghcr.io/srl-labs/clab@sha256:e48396f2245239216fc4a63c1bb5553425930f0beb1aac3e4c2dc3fda57da75f`:**
A minimal 2-node SR Linux topology deployed successfully via dood on Docker Desktop:
- both nodes reached `running`; containerlab created the veth link `n1:e1-1 ▪┄┄▪ n2:e1-1`;
- `ethernet-1/1` came up at L2 on both ends (veth operstate `up`) — wiring is real, not nominal;
- `containerlab destroy` removed both containers and the `clab` docker network cleanly;
- the lab **working directory** (`clab-<name>/`) is left on disk after destroy (see Consequences);
- the lab dir was created inside the repo, confirming the ADR-002 repo-only file share suffices.

## Decision

Run containerlab via dood, and **grant the Docker socket to the containerlab orchestrator container
only** — never to a lab node container, an application/service container, the workflow, the API, or
the executor. The exact invocation (recorded for reproducibility) is:

```
docker run --rm --privileged --network host \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /var/run/netns:/var/run/netns \
  -v /var/lib/docker/containers:/var/lib/docker/containers \
  --pid=host \
  -v <REPO>:<REPO> -w <REPO>/lab/generated \
  ghcr.io/srl-labs/clab@sha256:e48396f2... containerlab deploy|destroy -t <topo>.clab.yml
```

The socket-bearing container is ephemeral (`--rm`): it exists only for the duration of a
deploy/destroy invocation, not as a long-running service. No ClosCall application component (api,
workflow, correlator, sensor, executor, telemetry) ever receives the socket or these mounts.

## Alternatives

- **Dedicated Linux VM for the whole lab** (option 3 from the ADR-002 lineage). Strongest isolation
  — the socket lives in a VM separate from the app stack — but adds a second virtualization layer
  and tooling. Rejected *for now* because the spike proved dood workable and the socket container is
  ephemeral and orchestrator-only. **If dood had failed, falling back to a dedicated VM is a bigger
  call that STOPS for pilot ruling — it is not chosen silently.**
- **Native containerlab binary.** Impossible on macOS (needs Linux netlink).
- **Waving the socket through as a "documented exception"** (no ADR). Rejected: the socket is the
  highest-privilege capability in the build; it gets the same rigor as ADR-002.

## Residual risk

- Socket access ≈ root on the Docker VM. Anything running in the socket-bearing container could
  control every container in the VM. Containment: (1) only the orchestrator gets it; (2) it is
  ephemeral (`--rm`, deploy/destroy only); (3) the topology files it consumes are repo-authored and
  reviewed, not attacker-supplied (single-operator lab, threat-model §1/A1); (4) no untrusted input
  (LLM output, retrieved text) ever reaches the deploy invocation.
- This is a lab-orchestration privilege, entirely separate from the runtime device-mutation path
  (the executor, §2.6/§2.7), which never touches Docker and remains credential-bounded.
- Documented as a release limitation (J08 queue): lab orchestration uses a privileged, socket-
  bearing ephemeral container on the Docker Desktop VM, not a dedicated hypervisor.

## Migration

None — this is the initial lab-deployment mechanism. `make lab-up`/`lab-down` wrap the invocation
above. `lab-down` must also remove the leftover `clab-<name>/` working directory to satisfy B12.

## Affected tests

- B02–B12 (all network acceptance runs deploy/destroy through this mechanism).
- B12 teardown residue check must include the `clab-<name>/` working directory.
- Trust-boundary tests (H04/H05): assert no application/executor container holds the Docker socket.
