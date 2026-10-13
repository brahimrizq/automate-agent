.DEFAULT_GOAL := help
SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
.DELETE_ON_ERROR:

# Pass VERSION as data through the environment, never interpolate it into shell code.
export VERSION
GITLEAKS := ghcr.io/gitleaks/gitleaks:v8.30.1@sha256:c00b6bd0aeb3071cbcb79009cb16a60dd9e0a7c60e2be9ab65d25e6bc8abbb7f
TRIVY := aquasec/trivy:0.75.0@sha256:af6acf9a6b85dfe389a1941505c0ce9efef52a4719635e1a962f022a3d855daa

.PHONY: help check lint compose-check build build-mock test unit integration audit \
	scan-secrets image-export scan-image sbom versions release-check release release-status

help: ## List available development and release actions (default)
	@awk 'BEGIN {FS = ":.*## "; print "Usage: make <target> [VERSION=v0.1.0-alpha.3]\n"} /^[a-z-]+:.*## / {printf "  %-18s %s\n", $$1, $$2}' Makefile

check: ## Run lint, builds, all tests and the public-source audit
	scripts/check.sh

lint: ## Run containerized ShellCheck, shfmt, Hadolint and Compose checks
	scripts/lint.sh

compose-check: ## Validate the default and laboratory Compose configurations
	docker compose config --quiet
	docker compose -f compose.yaml -f compose.lab.yaml config --quiet

build: ## Build the dependency-only runtime as automate-agent:local
	docker build --target runtime -t automate-agent:local .

build-mock: ## Build the synthetic agent image for local tests only
	docker build --target mock -t automate-agent:mock .

test: unit integration ## Run unit and synthetic Docker integration tests

unit: build ## Run unit tests inside the dependency image
	docker run --rm --network none --read-only --tmpfs /tmp \
		-v "$$PWD:/src:ro" -w /src --entrypoint python3 automate-agent:local \
		-m unittest discover -s tests -p 'test_*.py' -v

integration: build build-mock ## Run synthetic integration tests; never execute vendor code
	python3 tests/integration.py

audit: ## Audit tracked public files for forbidden content and unpinned actions
	python3 scripts/check_public.py

scan-secrets: ## Scan complete Git history and local files with redacted output
	docker run --rm --network none -v "$$PWD:/src:ro" $(GITLEAKS) git /src --redact --log-opts=--all
	docker run --rm --network none -v "$$PWD:/src:ro" $(GITLEAKS) dir /src --redact

image-export: build ## Export the public dependency image into ignored artifacts/
	mkdir -p artifacts
	docker image save automate-agent:local -o artifacts/dependency-image.tar

scan-image: image-export ## Fail on HIGH/CRITICAL image vulnerabilities, including unfixed
	docker run --rm -v "$$PWD/artifacts:/input:ro" \
		-v automate-wrapper-trivy-cache:/root/.cache/trivy $(TRIVY) image \
		--input /input/dependency-image.tar --scanners vuln --severity HIGH,CRITICAL --exit-code 1

sbom: image-export ## Write artifacts/sbom.spdx.json for the local dependency image
	docker run --rm -v "$$PWD/artifacts:/input:ro" \
		-v automate-wrapper-trivy-cache:/root/.cache/trivy $(TRIVY) image \
		--input /input/dependency-image.tar --scanners vuln --format spdx-json > artifacts/sbom.spdx.json

versions: ## List local version tags, newest first (git fetch --tags to refresh)
	git tag --list 'v*' --sort=-version:refname

release-check: ## Check VERSION, clean/current main, changelog, unused tag and passing CI
	python3 scripts/release.py check

release: ## Check gates, then create and push VERSION to trigger signed publication
	python3 scripts/release.py publish

release-status: ## Show the GitHub release workflow and publication status for VERSION
	python3 scripts/release.py status
