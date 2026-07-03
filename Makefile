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
        secret-scan dep-audit sbom

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

# --- Later gates ---
test-contract test-integration test-security test-failure test-e2e \
db-up db-migrate db-reset-test lab-up lab-check lab-down traffic-smoke \
telemetry-up telemetry-check fault-smoke corpus-pilot corpus dataset-build \
dataset-verify train-rules train-ts train-gnn evaluate-sensors workflow-run \
api-up executor-up evaluate-agent evaluate-e2e nika demo reports:
	@$(NOT_READY)
