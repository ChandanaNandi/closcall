# ADR-002 — Lab runtime boundary (Docker Desktop vs. dedicated VM)

Status: accepted
Date: 2026-07-03

## Context

Bible §3.3 and §4 require that containerlab privileged operations run inside a dedicated, isolated
Linux VM, and §3.3 forbids mounting the Docker socket into application containers. The Gate 0 brief
named OrbStack as the runtime; that was an unverified planning-phase assumption (research log R10).
Observed reality: OrbStack is not installed; Docker Desktop 28.3.3 (client) / 29.1.3 (VM server) is
installed and canon-blessed (R2, Spec §9b lists "OrbStack/Docker Desktop"). The pilot ruled
Docker Desktop the runtime under "simplify, never add."

The open question (research log R8, retargeted in R10) is whether Docker Desktop's Linux VM meets
the pilot's intent standard for the "dedicated isolated VM" requirement:
**own kernel, own root boundary, and host filesystem not implicitly writable by lab containers.**

Evidence gathered 2026-07-03 (commands and outputs in session transcript):

1. **Own kernel — PASS.** The VM runs `Linux 6.12.54-linuxkit aarch64`, distinct from the macOS
   host (Darwin 25.5.0). Separate kernel, separate root filesystem.
2. **Unprivileged container isolation — PASS.** A default `alpine` container sees neither `/Users`
   nor `/Volumes`; its root filesystem is the container image only.
3. **Privileged escape to host files — FAIL at default settings.** Docker Desktop's default file
   sharing virtiofs-mounts the host `/Users`, `/Volumes`, `/private`, `/tmp`, `/var` **into the
   VM** (observed at `/host_mnt/*` inside the VM init mount namespace). containerlab runs
   **privileged** node containers; a privileged container can enter the VM init namespace
   (`--privileged --pid=host` + `nsenter -t 1 -m`) and from there read/write the host home
   directory at `/host_mnt/Users`. This is the "home-directory mount" gap the pilot flagged.

`settings-store.json` contains no `FilesharingDirectories` key, i.e. the shares are Docker
Desktop's built-in defaults, not an explicit choice. The authoritative signal is the VM's mount
table, not the config file (which is absent-at-default and whose schema varies by version).

## Decision

Docker Desktop **satisfies the intent standard conditionally** — the kernel and root boundaries are
genuine; the file-sharing gap is configuration, not an architectural property, so escalation to a
separate hypervisor VM (option 3) is not warranted. The condition is a host hardening step plus a
fail-closed gate check:

1. **Remove all host file-sharing entries** from Docker Desktop (Settings → Resources → File
   sharing: delete `/Users`, `/Volumes`, `/private`, `/tmp`, `/var/folders`), so no host path is
   present inside the VM. Lab topologies bind-mount only explicit, in-repo paths when a node needs
   one — never an implicit host tree.
2. **`make doctor` performs the adversarial ground-truth probe** a privileged lab container would
   use: enter the VM init mount namespace and assert that no `/host_mnt/<hostpath>` mount for a
   real host tree exists. Doctor **fails closed** if any host path is reachable. This checks the
   outcome (actual VM mounts), not Docker Desktop's config schema, so it survives version changes.
3. **Standing rule — no blanket `--privileged` (belt-and-suspenders, core).** No ClosCall lab
   container runs `--privileged` unless a specific capability is proven necessary and named in the
   topology. Where containerlab or a node kind requires specific capabilities (e.g. `NET_ADMIN`,
   `SYS_ADMIN` for netns/`tc` work), those caps are enumerated explicitly rather than granting
   blanket privilege. The minimum-capability posture for each node kind is verified when
   containerlab topologies are authored (Gate 2/3). **Finding to confirm at Gate 2/3:** the SR Linux
   containerlab node kind is widely run privileged; if containerlab forces full `--privileged` for
   SR Linux and it cannot be reduced to named caps, that is a residual risk to be recorded honestly
   here by a superseding note, not worked around.

Because the mitigation is a host-side setting the pilot applies (like CA trust and other sudo/GUI
steps), the pilot performs step 1; doctor (step 2) verifies it was actually done — the same
"attach the ruling to a gate check" pattern used for the disk-pressure item (R10).

## Residual risk

The two mitigations are complementary, and neither alone is sufficient:

- **Emptied file sharing** shrinks the virtiofs surface so no host tree is present in the VM for a
  container to reach. This is the primary control.
- **No-blanket-privileged** ensures a lab container does not casually hold the capability set that
  would let it enter the VM init namespace in the first place.

Residual risk, stated honestly: **a `--privileged` container plus host file-sharing = host files
reachable.** With file sharing emptied, a privileged container that escapes to the VM finds no host
tree mounted; with privilege reduced to named caps, the escape path itself is harder. If SR Linux
proves to require full privilege (Gate 2/3 finding), the residual is "privileged lab node + empty
file sharing": VM compromise is possible but yields no host filesystem access, which is the accepted
posture for a single-operator lab. This is not equivalent to a dedicated hypervisor VM and is
documented as such (README limitations, J08).

## Alternatives

- **Dedicated hypervisor VM for the lab (option 3).** Strongest isolation, but adds a second
  virtualization stack and new tooling for a boundary Docker Desktop already provides once file
  sharing is emptied. Rejected under "simplify, never add" unless the doctor probe cannot be made
  to pass. Available as the escalation path if step 1 does not remove the VM mounts.
- **Install OrbStack to match the original brief.** Rejected: not installed, not in the approved
  install set, and adds a second runtime alongside an existing one (pilot ruling, R10).
- **Accept the default shares and rely on not-using-privileged-containers.** Rejected: containerlab
  requires privileged nodes for SR Linux; the gap would be real and unguarded.

## Consequences

- `make doctor` gains a mandatory, fail-closed file-sharing probe; a machine with host paths shared
  into the VM cannot pass Gate 1.
- The release README limitations section must state that lab isolation depends on Docker Desktop
  file sharing being emptied, and that ClosCall does not defend against a host-privileged attacker
  (ties to threat-model A1, queued for J08).
- No new dependency or service is introduced.
- If a future lab node genuinely needs a host path, it must be an explicit, documented, in-repo
  bind mount, and the doctor probe's allowlist (empty by default) must be widened by a superseding
  ADR — never silently.

## Migration

1. Pilot empties Docker Desktop file sharing and restarts Docker Desktop.
2. `make doctor` re-run confirms zero host mounts in the VM.
3. If mounts persist after step 1, STOP and escalate to option 3 per the pilot's standing ruling.

## Affected tests

- `make doctor` (Gate 1 exit criterion "doctor reports exact capabilities") — gains the
  file-sharing probe.
- Supports acceptance rows in the I (security) family conceptually and the trust boundaries in
  `docs/threat-model.md` §2 (B-boundaries) / §5 (credential & host isolation).
- Bible §3.3 compliance (no implicit host exposure to lab containers).
