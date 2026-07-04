# ClosCall Makefile — required targets per Bible §15.
# Every target is non-interactive unless interaction is its purpose, returns
# non-zero on failure, and prints the artifact/run IDs it creates.
# Targets whose gate has not been reached fail explicitly rather than pretending.

.PHONY: doctor bootstrap lint typecheck test-unit test-contract test-integration \
        test-security test-failure test-e2e db-up db-migrate db-reset-test \
        lab-up lab-check lab-down traffic-smoke telemetry-up telemetry-check \
        fault-smoke corpus-pilot corpus dataset-build dataset-verify \
        train-rules train-ts train-gnn evaluate-sensors workflow-run api-up \
        executor-up evaluate-agent evaluate-e2e nika demo reports \
        secret-scan dep-audit sbom render fabric-validate render-validate pki \
        lab-up lab-down

NOT_READY = { echo "make $@: blocked — this target is implemented at a later gate" >&2; exit 2; }

bootstrap:
	uv sync --frozen
	uv run pre-commit install

lint:
	uv run ruff check .
	uv run ruff format --check .

typecheck:
	uv run mypy

test-unit:
	uv run pytest tests/unit tests/property

# --- Gate 1 helper targets (support the exit criterion: clean clone passes
# --- lint/types/unit/secret/dependency checks). Not part of the §15 list.
secret-scan:
	gitleaks git --redact .

dep-audit:
	uv run pip-audit --local

sbom:
	syft scan dir:. -o cyclonedx-json > artifacts/reports/sbom.cdx.json
	@echo "artifact: artifacts/reports/sbom.cdx.json"

doctor:
	python3.12 scripts/doctor.py

# --- Gate 2: topology/IPAM/config rendering ---
render:
	uv run python -c "from closcall.domain.fabric import load_fabric; from closcall.domain.render import render_all; import json; print(json.dumps(render_all(load_fabric('lab/fabric.yaml'),'lab/generated'), indent=2))"
	@echo "artifacts: lab/generated/ (see manifest.json)"

fabric-validate:
	uv run python -c "import sys; from closcall.domain.fabric import load_fabric; from closcall.domain.validate import validate_fabric; e=validate_fabric(load_fabric('lab/fabric.yaml')); [print('ERROR:',x) for x in e]; sys.exit(1 if e else 0)"
	@echo "fabric.yaml valid"

# Offline on-image config-parse check (needs Docker + pinned SR Linux image).
render-validate:
	uv run python scripts/validate_srl_configs.py

# Generate the local lab management PKI (host secret; gitignored, never committed).
pki:
	uv run python scripts/gen_pki.py

# --- Gate 3: deploy / acceptance / teardown (dood via ADR-003) ---
lab-up: render
	bash scripts/clab.sh deploy
	@echo "lab up: closcall-2s4l"

# Teardown must also remove the clab working directory (R18: destroy leaves it -> B12 residue).
lab-down:
	-bash scripts/clab.sh destroy
	rm -rf lab/generated/clab-closcall-2s4l
	@echo "lab down + working dir removed"

# Network acceptance checks B03-B08 against a running, converged fabric (§7.3).
lab-check:
	uv run python scripts/lab_check.py

# --- Gate 4: observation plane (gnmic + Prometheus) ---
telemetry-up:
	docker compose up -d
	@echo "telemetry up: Prometheus http://127.0.0.1:9090 (loopback)"

telemetry-down:
	docker compose down

telemetry-check:
	uv run python scripts/telemetry_check.py

# --- Gate 5: fault framework smoke campaign (needs fabric + telemetry up) ---
fault-smoke:
	uv run python scripts/fault_smoke.py

# --- Gate 6: database + deterministic vertical slice ---
db-up:
	docker compose up -d postgres

db-migrate:
	uv run alembic upgrade head

db-isolation:
	uv run python scripts/db_isolation_check.py

corpus:
	uv run python scripts/corpus_run.py

corpus-pilot:
	uv run python scripts/corpus_pilot.py

vertical-slice:
	uv run python scripts/vertical_slice.py

# --- Later gates ---
test-contract test-integration test-security test-failure test-e2e \
db-reset-test traffic-smoke \
corpus dataset-build \
dataset-verify train-rules train-ts train-gnn evaluate-sensors workflow-run \
api-up executor-up evaluate-agent evaluate-e2e nika demo reports:
	@$(NOT_READY)
