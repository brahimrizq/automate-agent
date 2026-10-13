# Testing and stable-release gate

## Public and local tests

Run `scripts/check.sh` from a Linux amd64 checkout with Docker, Compose, Bash,
Git and Python 3 already available. Docker downloads isolated lint/build tools;
no host package manager is invoked. Tests create only containers, images, internal
Docker networks and disposable volumes named `automate-test-*`. They never
execute the real installer or connect to an Automate endpoint. Fixture traffic
uses an internal Docker network without published ports.

Unit tests cover configuration, checksums, ELF architecture, archive traversal,
symlinks, absent inputs, initialization, locking, ownership/modes, identity
preservation, changed inputs, interrupted transactions, backup integrity,
upgrade/rollback, registration-target changes, log rotation and redaction.

Integration tests exercise actual native synthetic processes under the release
runtime: registration simulation, restart/recreation, separate identities,
exclusive volume use, crash exit propagation and bounded Docker restarts,
SIGTERM handling, stopped-but-live process health, DNS/network recovery,
log growth, maintenance commands, and public image content.

The mock's protocol and update behavior are deliberately not Automate's. A mock
reconnect does not prove vendor recovery. A SIGSTOP health failure does not prove
detection of an internally hung vendor process. Real agent-update support is
not claimed by a synthetic file replacement test.

## Private real-agent validation: not yet run

Use a disposable Ubuntu 24.04 amd64 VM, a dedicated Automate test location and
private enrollment files. Record OS/kernel, Docker/Compose versions, container
digest, private installer fingerprint and observed agent version. Do not publish
tenant identifiers, credentials or proprietary evidence.

1. Record `dpkg-query -W`, hostname, `/etc/os-release`, `lscpu`, `/proc/meminfo`,
   `findmnt`, `df`, `ps` and `systemctl list-units` before startup. Keep raw output private.
2. Enroll once; confirm identity, location and successful server acknowledgements.
   Recreate the container and prove the server retained the same computer record.
   Enroll a second disposable VM with a separate UUID/volume and prove distinct IDs.
3. Compare every requested property with server-side reports. Hostname, OS,
   logical CPU count, total memory, disk devices/mounts and capacities must match
   after unit conversion. Compare dynamic measurements at aligned sampling
   intervals; explain any tolerance. Match the host process/service inventories
   against the same observation window. Any unexplained discrepancy fails the gate.
4. Exercise DNS outage, packet loss, server outage, process crash and internal
   unresponsiveness. Record bounded recovery, registration count and reporting gaps.
5. Test active-work shutdown, certificate validation, secret rotation, native
   agent logs, disk usage, and state ownership. Confirm no host package/service
   changes attributable to the wrapper by comparing the baseline.
6. Test manual upgrades, snapshot rollback and vendor-triggered update paths,
   including server-forced updates. Record incompatible state/server changes.
7. Measure CPU, RSS, process count, disk growth and host reports with and without
   proposed resource limits. Limits must support the workload without changing
   collected host totals or preventing timely reporting.
8. Run at least seven continuous days after the preceding checks pass, including
   a VM reboot and deliberate fault recovery. Record actual start/end timestamps,
   duration, versions, failures, data gaps and resource peaks. A short smoke test
   is never described as a soak test.

A stable-release change must include sanitized evidence for every gate, resolve
all host-metric discrepancies, and explicitly update the prerelease-only workflow
guard. Never test with broad privileges on a production server.
