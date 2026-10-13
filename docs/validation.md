# Validation record — 2026-10-13

These are completed local checks for the experimental wrapper, not real-agent
compatibility or production certification.

| Check | Observed result |
| --- | --- |
| Runtime image | Ubuntu 24.04, linux/amd64, built successfully from pinned base. |
| Local Docker / Compose | Docker Engine 29.8.1; Compose 5.5.1. |
| ShellCheck / shfmt / Hadolint | Passed using pinned tool containers. |
| Compose default and lab configurations | Both validated. |
| Unit tests | 26 passed, including archive safety, identity locks, malformed metadata and snapshot rollback. |
| Docker integration tests | 13 passed in 29.267 seconds on the corrective local run, including user-owned private-file and backup-directory access. |
| Crash recovery | Synthetic exit 42 retained; Docker stopped after two configured retries; later restart reused identity. |
| Network/DNS faults | Internal synthetic endpoint unavailable, available, disconnected and reconnected; identity retained. |
| Graceful shutdown / unhealthy process | Synthetic SIGTERM completed; SIGSTOP was unhealthy and SIGCONT recovered. |
| Maintenance | Container backup, explicit upgrade and snapshot restore preserved synthetic identity. |
| Logs | Synthetic capture redacted enrollment text; native log rotation stayed within the test's 15 MiB transient bound per file and four-file count. |
| Resource limits | Synthetic integration suite ran at 1 CPU, 512 MiB and 256 PIDs. Real-agent limits and metric accuracy remain unverified. |
| Public source audit | Tracked files checked for binary/archive/private-path content and unpinned workflow actions. |
| Secret scan | Gitleaks working-tree scan passed with redacted output. Complete history is also scanned before publication and in CI. |
| Image vulnerabilities | Trivy 0.75.0 found zero HIGH/CRITICAL vulnerabilities in 109 detected Ubuntu packages; unfixed findings were not suppressed. |
| Actual private ZIP | Static wrapper validation accepted layout and ELF architecture without executing any vendor code. |
| Private reporting | Enabled and verified via GitHub API. |
| Private file permissions | Synthetic user-owned mode-0600 file was unreadable with no capabilities and readable with `DAC_OVERRIDE`; the corrective Compose profile adds only that capability. |

Public CI independently repeats checks and publishes an SBOM. See the
[CI runs](https://github.com/brahimrizq/automate-agent/actions/workflows/ci.yaml)
and [release runs](https://github.com/brahimrizq/automate-agent/actions/workflows/release.yaml)
for commit-specific status; links do not imply a passing run.

## Explicitly not verified

Real enrollment and check-ins; actual-host hostname, OS, CPU, memory, disks,
processes, services and package reports; real-agent graceful shutdown and network
recovery; optional downloaded components; vendor automatic/server-forced updates;
server-side rollback; TLS interoperability; unchanged VM package inventory;
real-agent resource requirements; and continuous operation.

No disposable VM or dedicated Automate test location was available. No real
agent was executed on the development host. **Real-agent soak duration: zero.**
The short synthetic suite is not a soak test. Stable promotion requires the
separate seven-day validation protocol in [testing.md](testing.md).
