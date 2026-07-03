# ClosCall — Toolchain Register

Every dependency, image, and tool used by this project is recorded here with its exact pinned
version as observed on the build machine, plus a link to its primary documentation. "Latest" tags
are forbidden (Bible §4). Fast-moving external repositories are cited by commit SHA only, in
`research/source-register.md` (README source-pinning policy A1).

| Tool | Exact version (observed) | Verified by | Date (UTC) | Primary docs |
|---|---|---|---|---|
| git | 2.50.1 (Apple Git-155) | `git --version` on build host | 2026-07-03 | https://git-scm.com/docs |
| Python | 3.12.12 | `python3.12 --version` | 2026-07-03 | https://docs.python.org/3.12/ |
| uv | 0.7.21 | `uv --version` | 2026-07-03 | https://docs.astral.sh/uv/ |
| Docker Desktop (docker CLI) | 28.3.3 (client) | `docker --version` | 2026-07-03 | https://docs.docker.com/desktop/ |
| gh | 2.92.0 | `gh --version` | 2026-07-03 | https://cli.github.com/manual/ |
| gitleaks | 8.30.1 | `gitleaks version` | 2026-07-03 | https://github.com/gitleaks/gitleaks |
| syft | 1.46.0 | `syft version` | 2026-07-03 | https://github.com/anchore/syft |
| trivy | 0.72.0 | `trivy --version` | 2026-07-03 | https://trivy.dev/latest/docs/ |
| caddy | 2.11.4 | `caddy version` | 2026-07-03 | https://caddyserver.com/docs/ |

### Container images (pinned by digest)

| Image | Digest | Used by | Date (UTC) | Primary docs |
|---|---|---|---|---|
| alpine 3.22 | `sha256:14358309a308569c32bdc37e2e0e9694be33a9d99e68afb0f5ff33cc1f695dce` | `make doctor` VM/file-sharing probe | 2026-07-03 | https://hub.docker.com/_/alpine |

Python dependencies are pinned exactly by the committed `uv.lock` (`uv sync --frozen` everywhere,
including CI). Key locked versions at Gate 1: pydantic 2.13.4, pydantic-settings 2.14.2,
ruff 0.15.20, mypy 2.1.0, pytest 9.1.1, hypothesis 6.156.1, pip-audit 2.10.1, pre-commit 4.6.0.

GitHub Actions are pinned by full commit SHA in `.github/workflows/ci.yml`:
actions/checkout v7.0.0 `9c091bb2…`, astral-sh/setup-uv v8.2.0 `fac544c0…`,
gitleaks/gitleaks-action v3.0.0 `e0c47f4f…`.

Build host: Apple Silicon macOS 26.5.2 (Darwin 25.5.0), 24 GB RAM, 12 cores. Additional tools are
added at the gate where they are first used, never earlier.
