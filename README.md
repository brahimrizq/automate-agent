# Automate agent container wrapper — experimental

[![CI](https://github.com/brahimrizq/automate-agent/actions/workflows/ci.yaml/badge.svg)](https://github.com/brahimrizq/automate-agent/actions/workflows/ci.yaml)

An independent, unofficial Docker wrapper for a privately supplied ConnectWise
Automate Linux agent. Not affiliated with, endorsed by, or supported by ConnectWise.

**This prerelease does not establish accurate host monitoring.** The agent reads
namespace-sensitive system information. The isolated default can report container
information, cannot see host services, and has not been enrolled against a live
Automate server. Do not deploy it as a production host-monitoring solution.
See the [feasibility report](docs/feasibility.md) and [validation record](docs/validation.md).

The public image contains Ubuntu runtime dependencies and original wrapper code
only. No proprietary installer, registered identity, or customer configuration is
included. The inspected agent is native x86-64; no Java dependency was identified
for its core process. Optional remote-control features are outside this release.

## Quick start: authorized disposable environment only

Prerequisites: Linux amd64, Docker Engine with Compose v2+, your licensed x86-64
installer ZIP, and a dedicated Automate test location. Ubuntu 24.04 is the first
real-agent validation target, not a tested compatibility claim.

```sh
git clone https://github.com/brahimrizq/automate-agent.git
cd automate-agent
cp .env.example .env
mkdir -p "$HOME/.local/share/automate-agent-private"
chmod 700 "$HOME/.local/share/automate-agent-private"
cp config.example "$HOME/.local/share/automate-agent-private/agent_config"
chmod 600 "$HOME/.local/share/automate-agent-private/agent_config"
```

Keep your installer ZIP outside this checkout. In the private configuration file,
replace `server_url`, `system_password`, and `location_id` with your test enrollment
values. The corresponding installer assignments are `LT_SERVER_ADDRESS`,
`LT_SYSTEM_PASSWORD`, and `LT_LOCATION_ID`; inspect them privately without running
or sourcing the script. Never paste them into an issue or commit them.

Generate a unique host instance ID and calculate the archive checksum:

```sh
cat /proc/sys/kernel/random/uuid
sha256sum '/absolute/private/path/LTechAgent_x86_64.zip'
```

Edit `.env`: set absolute `INSTALLER_PATH` and `AGENT_CONFIG_PATH`, the checksum in
`INSTALLER_SHA256`, the UUID in `AGENT_INSTANCE_ID`, and `ACCEPT_EXPERIMENTAL=yes`.
Keep the same UUID and state volume through restarts. Use a new UUID and volume
for each additional host; never clone a registered volume.

```sh
scripts/agentctl build
scripts/agentctl init       # validates and stages files; does not execute the agent
scripts/agentctl start      # executes the agent; may enroll immediately
scripts/agentctl status
scripts/agentctl logs
scripts/agentctl stop
```

`status` distinguishes process health from communication, which remains `unknown`.
Only server-side observation can establish successful registration and check-ins
for this release. Use `docker compose -f compose.yaml -f compose.lab.yaml up -d
--no-build` for the provisional laboratory limits; they are not validated for
real-agent operation or metric accuracy.

## Upgrade and rollback

Read [the complete procedure](docs/upgrades.md) before upgrading. Preserve both
the old and new private installer/configuration files and wrapper image digests.

```sh
# Stop first; then update .env to the NEW installer/checksum and wrapper image.
scripts/agentctl stop
mkdir -m 700 /absolute/private/new-backup-directory
scripts/agentctl upgrade /absolute/private/new-backup-directory
scripts/agentctl start
scripts/agentctl status
```

The upgrade command takes a complete backup before replacing payload files. It
does not start the agent. On failure, leave it stopped and restore:

```sh
scripts/agentctl stop
# Restore the OLD installer/configuration paths, checksum and image digest in .env.
scripts/agentctl restore /absolute/private/new-backup-directory
scripts/agentctl start
```

Never use `docker compose down -v` for routine maintenance: it deletes identity.
Backups contain credentials and vendor software; keep them private and encrypted
at rest. Runtime automatic updates are unsupported; `auto_update no` is enforced
at startup but server-forced updates remain unverified.

## Published images and verification

Release images use `ghcr.io/brahimrizq/automate-agent:v0.1.0-alpha.1`. Prefer the
immutable `@sha256:...` reference recorded in each release. Set `WRAPPER_IMAGE` to
that reference, run `docker compose pull agent`, then use the same initialization
and startup commands. Source builds use `automate-agent:local`.

See [release signing and provenance](docs/releases.md). There is no stable or
`latest` tag. Passing public CI establishes wrapper behavior with synthetic
fixtures, not vendor-agent compatibility.

## Troubleshooting

| Event or symptom | Action |
| --- | --- |
| `explicit_experimental_opt_in_required` | Read the limitations, then set `ACCEPT_EXPERIMENTAL=yes` only for an authorized lab. |
| `installer_checksum_mismatch` | Calculate the supplied archive's SHA-256; keep it outside the checkout. |
| `configuration_invalid` | Use the documented private config format; credentials are deliberately omitted from error output. |
| `state_already_in_use` | Stop the other container using this volume. Never remove a live lock file. |
| `inputs_changed_explicit_upgrade_required` | Follow the backup/upgrade procedure, including for credential rotation. |
| `interrupted_transaction_restore_required` | Stop and restore a verified snapshot; do not delete registration state. |
| Process healthy, Automate offline | Health does not prove communication. Check the server, DNS, TLS and private diagnostics. |
| Incorrect host metrics | Expected possibility in this experimental design. Do not add privileges blindly. |

Native diagnostics stay in the private volume. Wrapper stdout contains only
fixed lifecycle events and numeric process details. Do not upload raw logs or
snapshots. See [configuration](docs/configuration.md), [architecture](docs/architecture.md),
[host access](docs/host-access.md), and [testing](docs/testing.md).

## Development and license

Run `scripts/check.sh`; it uses Docker for compilers, linters and unit tests, with
the existing host Python 3 interpreter only orchestrating Docker integration
tests. No real credentials are needed. See [CONTRIBUTING.md](CONTRIBUTING.md).

[MIT](LICENSE) covers only original wrapper code, documentation and synthetic
fixtures. Vendor software is excluded; users must obtain it under their own
license. Report vulnerabilities through [SECURITY.md](SECURITY.md).
