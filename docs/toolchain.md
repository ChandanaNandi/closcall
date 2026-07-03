# ClosCall — Toolchain Register

Every dependency, image, and tool used by this project is recorded here with its exact pinned
version as observed on the build machine, plus a link to its primary documentation. "Latest" tags
are forbidden (Bible §4). Fast-moving external repositories are cited by commit SHA only, in
`research/source-register.md` (README source-pinning policy A1).

| Tool | Exact version (observed) | Verified by | Date (UTC) | Primary docs |
|---|---|---|---|---|
| git | 2.50.1 (Apple Git-155) | `git --version` on build host | 2026-07-03 | https://git-scm.com/docs |

Build host: Apple Silicon macOS (Darwin 25.5.0). Additional tools are added at the gate where they
are first used, never earlier.
