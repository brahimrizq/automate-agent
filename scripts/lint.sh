#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
docker run --rm --network none -v "$PWD:/src:ro" -w /src \
  koalaman/shellcheck:v0.11.0@sha256:61862eba1fcf09a484ebcc6feea46f1782532571a34ed51fedf90dd25f925a8d \
  scripts/agentctl scripts/lint.sh scripts/check.sh
docker run --rm --network none -v "$PWD:/src:ro" -w /src \
  mvdan/shfmt:v3.14.1@sha256:8c06884a35683d8763fba6c0d9484d11a61a96da65f8d497d6f625825a6043f2 \
  -d -i 2 -ci scripts/agentctl scripts/lint.sh scripts/check.sh
docker run --rm --network none -i \
  hadolint/hadolint:v2.15.1@sha256:32dac94127fd60b7b7e3fbfc65e1383b9b5e25c9bfd7b8536de7a539fe68a12d <Dockerfile
docker compose config --quiet
docker compose -f compose.yaml -f compose.lab.yaml config --quiet
