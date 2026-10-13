# Host access and limitations

The default requires **no host namespaces, host system mounts, device access,
extra Linux capabilities, Docker socket, or host service socket**. The only
inputs are two private read-only files and one writable Docker state volume.
The container root filesystem is read-only; bounded tmpfs mounts support temporary
files and supervisor health status. Root is retained inside the isolated
container to match the inspected installer file ownership; all capabilities are
dropped and privilege escalation is disabled. Root here is not evidence that
host management works.

Maintaining a backup temporarily mounts only the operator-selected backup
directory, writable for backup and read-only for restore. Docker administration
itself requires appropriate operator privileges; the agent never receives the
Docker socket.

The default cannot accurately inventory host services, packages or processes.
Host networking alone cannot fix filesystem metrics; host PID access alone
cannot fix mount paths or OS files; mounting `/proc` elsewhere is ineffective
unless the agent actually reads that path. Sharing the host mount namespace
would expose dependencies and mutation risks inconsistent with this design.

Do not mount the host systemd/D-Bus socket as a workaround: a read-only mount
does not restrict RPC methods. Do not use `privileged: true`, writable host-root
mounts, or host Java/library installation.

Future experiments must occur on a disposable Ubuntu VM. Change one access
mechanism at a time, record the exact need and permission, compare all metrics,
and reject an access change that merely makes the agent connect without fixing
accuracy. No optional host-access Compose profile is shipped before those tests.
