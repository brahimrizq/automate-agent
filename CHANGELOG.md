# Changelog

## 0.1.0-alpha.2 — 2026-10-13

- Fix access to user-owned mode-0600 secret files and mode-0700 backup directories
  by adding only the tested `DAC_OVERRIDE` capability after dropping all others.
- Add a Docker regression test for private bind-mounted input and backup access.
- Document the capability's purpose and limits. The earlier release tag remains unchanged.

## 0.1.0-alpha.1 — 2026-10-13

- Initial unofficial, experimental dependency-only container wrapper.
- Private runtime installer/config inputs, archive/ELF validation and TLS policy.
- Persistent identity locking, process supervision, private bounded diagnostics,
  local health reporting, explicit upgrades and snapshot rollback.
- Synthetic unit/integration tests and CI, scanning, SBOM and signed-release workflows.
- No claim of real-agent compatibility, accurate host monitoring, automatic-update
  support, production readiness or completed soak validation.
