# Configuration and operations

| Input | Meaning |
| --- | --- |
| `INSTALLER_PATH` | Absolute host path to the private ZIP, mounted read-only by Compose. |
| `AGENT_CONFIG_PATH` | Absolute host path to private configuration, mounted read-only. |
| `INSTALLER_SHA256` | Required SHA-256; detects accidental replacement, not vendor authenticity. Obtain the archive through your trusted vendor channel. |
| `AGENT_INSTANCE_ID` | Unique UUID per host, stable across recreation; stored in the volume. |
| `ACCEPT_EXPERIMENTAL` | Must equal `yes` before any operation. |
| `WRAPPER_IMAGE` | Local image or immutable GHCR digest. |
| `SHUTDOWN_SECONDS` | Supervisor timeout, 60 seconds in Compose. If changed, increase `stop_grace_period` to at least timeout + 15 seconds. |

Inside the container, `INSTALLER_FILE` and `AGENT_CONFIG_FILE` default to
`/run/secrets/installer.zip` and `/run/secrets/agent_config`. These overrides are
used for test fixtures, not for embedding credentials in environment variables.

The private config is one key and one whitespace-free value per line. Blank
lines and full-line comments are allowed. Duplicate/unknown keys are refused.
Required fields are `server_url` (HTTPS URL without embedded credentials, query
or fragment), `system_password`, and numeric `location_id`. `ssl yes`,
`ssl_verify_cert yes`, and `auto_update no` are enforced. No shell evaluation,
interpolation, or escape expansion occurs. A secret requiring whitespace needs
separate vendor-format investigation rather than silent alteration.

`init`, `run`, `upgrade`, `backup`, and `restore` are the container commands.
`scripts/agentctl` provides host-side Docker orchestration. Exit 78 means invalid
configuration/state, 70 a local operation failure, and child exits are retained
(signal exits use 128 + signal number). Transient process-launch resource errors
retry at 1, 2 and 4 seconds. Other launch errors fail. Agent crashes are handled
by Compose's bounded `on-failure:5` restart policy; failed configuration also
consumes that budget. Exhaustion requires operator intervention. This policy
does not restart containers simply because a health check is unhealthy and does
not provide automatic restart following every host/daemon reboot; start explicitly
after reboot and verify health. See [Docker restart behavior](https://docs.docker.com/engine/containers/start-containers-automatically/).

No arbitrary production resource ceiling is asserted. `compose.lab.yaml` provides
1 CPU, 512 MiB RAM and 256 PIDs for synthetic tests. These are provisional and
may distort real agent results or reject legitimate work. Follow the real-agent
measurement gate before choosing deployment limits.

Lifecycle stdout uses fixed JSON events, with Docker rotation at 10 MiB × 3.
Agent stdout/stderr is captured privately and redacted using known config/state
secrets plus credential field patterns. It is not mirrored into Docker logs.
Known top-level `.log`/`.debug` files are copy-truncated at 10 MiB, retaining three
archives. Native files remain sensitive; redaction is not a guarantee for encoded
or unknown secrets. Rotation can lose diagnostics during concurrent writes and
can temporarily overshoot its threshold. Other downloaded files are not subject
to log quotas. Monitor volume usage during authorized validation.
