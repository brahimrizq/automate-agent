#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
scripts/lint.sh
docker build --target runtime -t automate-agent:local .
docker run --rm --network none --read-only --tmpfs /tmp \
  -v "$PWD:/src:ro" -w /src --entrypoint python3 automate-agent:local \
  -m unittest discover -s tests -p 'test_*.py' -v
docker build --target mock -t automate-agent:mock .
python3 tests/integration.py
python3 scripts/check_public.py
