import hashlib
import io
import json
import os
from pathlib import Path
import stat
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import uuid
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "wrapper"))
import agentwrap as w


def elf(machine=62):
    data = bytearray(64)
    data[:7] = b"\x7fELF\x02\x01\x01"
    data[16:18] = (3).to_bytes(2, "little")
    data[18:20] = machine.to_bytes(2, "little")
    return bytes(data)


class WrapperTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.state = self.root / "state-dir"
        self.state.mkdir()
        self.identity = str(uuid.uuid4())
        self.values = w.config(b"server_url https://automate.example.invalid\n"
                               b"system_password synthetic-enrollment\nlocation_id 1\n")
        self.payload = {name: elf() for name in w.PAYLOAD}
        self.payload["uninstaller.sh"] = b"#!/bin/sh\nexit 99\n"

    def initialize(self):
        return w.prepare(self.state, self.identity, self.payload, self.values, "a" * 64)

    def archive(self, extra=None, machine=62):
        path = self.root / "installer.zip"
        with zipfile.ZipFile(path, "w") as archive:
            for name in w.PAYLOAD:
                archive.writestr("LTechAgent/data/" + name, elf(machine))
            if extra:
                archive.writestr(*extra)
        return path, hashlib.sha256(path.read_bytes()).hexdigest()

    def test_config_enforces_tls_and_manual_updates(self):
        self.assertEqual(self.values["ssl_verify_cert"], "yes")
        self.assertEqual(self.values["auto_update"], "no")

    def test_invalid_config(self):
        base = w.config_bytes(self.values)
        for bad in [b"", base + b"location_id 2\n", base.replace(b"https://", b"http://"),
                    base.replace(b"ssl_verify_cert yes", b"ssl_verify_cert no"),
                    base.replace(b"auto_update no", b"auto_update yes"),
                    base.replace(b"location_id 1", b"location_id nope"),
                    base.replace(b"automate.example.invalid", b"user:password@example.invalid"),
                    base + b"command /bin/sh\n", b"\xff"]:
            with self.subTest(data=bad), self.assertRaises(w.Invalid):
                w.config(bad)

    def test_checksum_required(self):
        path, _ = self.archive()
        with self.assertRaises(w.Invalid):
            w.read_payload(path, "0" * 64)

    def test_archive_valid(self):
        self.assertEqual(set(w.read_payload(*self.archive())), set(w.PAYLOAD))

    def test_archive_wrong_architecture(self):
        with self.assertRaises(w.Invalid):
            w.read_payload(*self.archive(machine=183))

    def test_archive_traversal_absolute_and_symlink(self):
        link = zipfile.ZipInfo("LTechAgent/data/link")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        for name in ["../outside", "/absolute", "a\\b", link]:
            with self.subTest(name=name), self.assertRaises(w.Invalid):
                w.read_payload(*self.archive((name, b"target")))

    def test_archive_missing_payload(self):
        path = self.root / "empty.zip"
        with zipfile.ZipFile(path, "w"):
            pass
        with self.assertRaises(w.Invalid):
            w.read_payload(path, w.digest(path.read_bytes()))

    def test_missing_and_symlink_input(self):
        with self.assertRaises(w.Invalid):
            w.regular(self.root / "missing")
        (self.root / "link").symlink_to(__file__)
        with self.assertRaises(w.Invalid):
            w.regular(self.root / "link")

    def test_initialization_idempotent_and_private(self):
        self.assertTrue(self.initialize())
        w.atomic(self.state / "state", b"private-identity")
        self.assertFalse(self.initialize())
        self.assertEqual((self.state / "state").read_bytes(), b"private-identity")
        self.assertEqual(stat.S_IMODE((self.state / "agent_config").stat().st_mode), 0o600)

    def test_other_instance_refused(self):
        self.initialize()
        with self.assertRaises(w.Invalid):
            w.metadata(self.state, str(uuid.uuid4()))

    def test_lock_excludes_concurrent_use(self):
        with w.StateLock(self.state):
            with self.assertRaises(w.Invalid):
                with w.StateLock(self.state):
                    pass
        with w.StateLock(self.state):
            pass

    def test_partial_state_refused(self):
        (self.state / "state").write_text("existing")
        with self.assertRaises(w.Invalid):
            self.initialize()

    def test_interrupted_transaction_refused(self):
        self.initialize()
        (self.state / w.TRANSACTION).touch()
        with self.assertRaises(w.Invalid):
            self.initialize()

    def test_changed_payload_refused(self):
        self.initialize()
        (self.state / "ltechagent").chmod(0o700)
        (self.state / "ltechagent").write_bytes(b"changed")
        with self.assertRaises(w.Invalid):
            self.initialize()

    def test_changed_inputs_require_upgrade(self):
        self.initialize()
        with self.assertRaises(w.Invalid):
            w.prepare(self.state, self.identity, self.payload, self.values, "b" * 64)

    def test_malformed_metadata_refused_without_deleting_identity(self):
        self.initialize()
        (self.state / "state").write_bytes(b"keep-identity")
        for value in [[], {"schema": 1, "instance_id": self.identity, "payload": []}]:
            w.json_write(self.state / w.META, value)
            with self.assertRaises(w.Invalid):
                w.metadata(self.state, self.identity)
            self.assertEqual((self.state / "state").read_bytes(), b"keep-identity")

    def test_upgrade_retains_identity_and_rollback_restores_snapshot(self):
        self.initialize()
        (self.state / "state").write_bytes(b"identity-before-upgrade")
        destination = self.root / "snapshot.tar"
        w.backup(self.state, destination, self.identity)
        new = dict(self.payload, ltupdate=elf() + b"new")
        w.prepare(self.state, self.identity, new, self.values, "b" * 64, upgrade=True)
        self.assertEqual((self.state / "state").read_bytes(), b"identity-before-upgrade")
        (self.state / "state").write_bytes(b"new-state-format")
        (self.state / w.TRANSACTION).touch()
        w.restore(self.state, destination, self.identity)
        self.assertEqual((self.state / "state").read_bytes(), b"identity-before-upgrade")
        self.assertEqual(w.metadata(self.state, self.identity)["installer_sha256"], "a" * 64)

    def test_backup_does_not_overwrite(self):
        self.initialize()
        path = self.root / "snapshot.tar"
        w.backup(self.state, path, self.identity)
        with self.assertRaises(w.Invalid):
            w.backup(self.state, path, self.identity)

    def test_wrong_snapshot_identity_does_not_destroy_state(self):
        self.initialize()
        path = self.root / "snapshot.tar"
        w.backup(self.state, path, self.identity)
        with self.assertRaises(w.Invalid):
            w.restore(self.state, path, str(uuid.uuid4()))
        w.metadata(self.state, self.identity)

    def test_corrupt_snapshot_does_not_destroy_state(self):
        self.initialize()
        path = self.root / "snapshot.tar"
        w.backup(self.state, path, self.identity)
        path.write_bytes(b"bad")
        with self.assertRaises(w.Invalid):
            w.restore(self.state, path, self.identity)
        w.metadata(self.state, self.identity)

    def test_snapshot_traversal(self):
        self.initialize()
        path = self.root / "snapshot.tar"
        with tarfile.open(path, "w") as archive:
            member = tarfile.TarInfo("../escape")
            member.size = 1
            archive.addfile(member, io.BytesIO(b"x"))
        Path(str(path) + ".sha256").write_text(w.digest(path.read_bytes()))
        with self.assertRaises(w.Invalid):
            w.restore(self.state, path, self.identity)
        w.metadata(self.state, self.identity)

    def test_new_registration_target_refused_on_upgrade(self):
        self.initialize()
        with self.assertRaises(w.Invalid):
            w.prepare(self.state, self.identity, self.payload, dict(self.values, location_id="2"),
                      "b" * 64, upgrade=True)

    def test_log_rotation_bounded(self):
        path = self.root / "agent.log"
        for _ in range(7):
            path.write_bytes(b"x" * 20)
            w.rotate(path, limit=10)
        self.assertEqual(path.stat().st_size, 0)
        self.assertEqual(len(list(self.root.glob("agent.log.*"))), 3)
        self.assertEqual(Path(str(path) + ".1").read_bytes(), b"x" * 10)

    def test_redaction(self):
        output = w.redact("password=unknown synthetic-enrollment", ["synthetic-enrollment"])
        self.assertNotIn("unknown", output)
        self.assertNotIn("synthetic-enrollment", output)

    def test_health_missing_status_is_not_healthy(self):
        result = w.health(self.state, self.root / "missing")
        self.assertEqual(result["process"], "unhealthy")
        self.assertEqual(result["communication"], "unknown")

    def test_opt_in_required(self):
        with patch.dict(os.environ, {"ACCEPT_EXPERIMENTAL": "no"}):
            self.assertEqual(w.main(["init"]), 78)


if __name__ == "__main__":
    unittest.main()
