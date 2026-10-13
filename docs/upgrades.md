# Upgrade and rollback

Image upgrades change the wrapper/dependencies. Agent upgrades change privately
supplied payload files. These are separate operations; changing the public image
alone does not replace the persistent agent. Automatic vendor updates are
unsupported: the observed updater expects installation and service commands.
The static `auto_update no` option is enforced, but no live evidence establishes
server-forced update behavior. If payload hashes change unexpectedly, startup
refuses and requires explicit recovery.

## Before any change

1. Record the current immutable wrapper image digest, installer checksum,
   configuration path, instance UUID and Compose project name privately.
2. Keep the old installer and config alongside the new versions, outside Git.
3. Stop with `scripts/agentctl stop`. Never run two copies of an identity.
4. Create a new private directory: `mkdir -m 700 /absolute/private/backup-001`.
5. For an image-only change, run `scripts/agentctl backup /absolute/private/backup-001`
   before replacing the image reference. For a payload/config change, use the
   upgrade command below; it makes the backup before staging the replacement.

## Payload or enrollment-secret upgrade

Update `.env` to point to the new ZIP, checksum and private config. Keep the same
UUID, server and location. Then:

```sh
scripts/agentctl upgrade /absolute/private/backup-001
scripts/agentctl start
scripts/agentctl status
```

The backup command reads the existing installed state, independently of the new
installer/config values. `snapshot.tar` and `snapshot.tar.sha256` must not already
exist. Treat any failure as a stopped deployment; do not remove the transaction
marker. Backups include vendor binaries, state and credentials, and are created
root-owned with mode 600. Access them only through authorized administrative
tools, encrypt copies, and never upload them to public CI or support issues.

## Wrapper image upgrade

After backup, change `WRAPPER_IMAGE` to the new verified digest in `.env`, run
`docker compose pull agent`, then `scripts/agentctl start`. For local source
builds, preserve the old image by digest before `scripts/agentctl build`. No
automatic state migrations are performed; metadata schema mismatches fail.

## Rollback

Stop, restore the old installer/config/checksum and wrapper image digest in
`.env`, and ensure that image is available. Then:

```sh
scripts/agentctl restore /absolute/private/backup-001
scripts/agentctl start
scripts/agentctl status
```

Restore validates checksum, archive safety, metadata, instance ID and payload
hashes before replacing current state. It requires enough state-volume space for
both the snapshot contents and the existing installation. Snapshot size is
limited to 1 GiB. If restore is interrupted, repeat it from the intact backup.
Do not restore a snapshot onto a second concurrently active host.

Synthetic tests cover local restore mechanics. Vendor state backward
compatibility and server-side rollback remain unverified; restoring a snapshot
cannot roll back changes already made on the Automate server.
