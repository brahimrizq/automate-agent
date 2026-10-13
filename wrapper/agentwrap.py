"""Original container wrapper. Vendor software is supplied privately at runtime."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import selectors
import shutil
import signal
import stat
import subprocess
import tarfile
import tempfile
import time
from urllib.parse import urlsplit
import uuid
import zipfile

STATE = Path("/usr/local/ltechagent")
STATUS = Path("/run/wrapper/status.json")
PAYLOAD = ("ltechagent", "libltech.so", "ltupdate", "uninstaller.sh")
META = ".wrapper.json"
LOCK = ".wrapper.lock"
TRANSACTION = ".wrapper-transaction"
MAX_ARCHIVE = 128 * 1024 * 1024
MAX_SNAPSHOT = 1024 * 1024 * 1024
LOG_LIMIT = 10 * 1024 * 1024


class Invalid(Exception):
    """Messages are fixed strings; never interpolate vendor or secret input."""


def event(name, **fields):
    print(json.dumps({"event": name, **fields}, sort_keys=True), flush=True)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def atomic(path, data):
    """Durable replacement in the destination directory, always private."""
    path = Path(path)
    fd, tmp = tempfile.mkstemp(prefix=".wrapper-write-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def json_write(path, value):
    atomic(path, json.dumps(value, sort_keys=True).encode())


def regular(path, maximum=MAX_ARCHIVE):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise Invalid("required_regular_file_missing")
    if path.stat().st_size > maximum:
        raise Invalid("input_too_large")
    return path.read_bytes()


def config(data):
    """Parse data, never shell code. No credentials in build args or argv."""
    if len(data) > 65536:
        raise Invalid("configuration_too_large")
    values = {}
    try:
        for line in data.decode("utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, value = line.split(None, 1)
            if key in values or key not in {
                "server_url", "system_password", "location_id",
                "ssl", "ssl_verify_cert", "auto_update"}:
                raise Invalid("configuration_key_invalid_or_duplicate")
            if any(ord(c) < 33 or ord(c) == 127 for c in value):
                raise Invalid("configuration_value_invalid")
            values[key] = value
        url = urlsplit(values["server_url"])
        if (url.scheme != "https" or not url.hostname or url.username
                or url.password or url.query or url.fragment):
            raise Invalid("server_url_requires_https_without_embedded_credentials")
        if url.port is not None and not 1 <= url.port <= 65535:
            raise Invalid("server_port_invalid")
        if not values["system_password"] or values["system_password"].startswith("REPLACE_"):
            raise Invalid("enrollment_secret_missing")
        if not re.fullmatch(r"[0-9]{1,10}", values["location_id"]):
            raise Invalid("location_id_invalid")
    except (UnicodeError, ValueError, KeyError):
        raise Invalid("configuration_invalid") from None
    for key, expected in {"ssl": "yes", "ssl_verify_cert": "yes", "auto_update": "no"}.items():
        if values.get(key, expected) != expected:
            raise Invalid("unsafe_configuration_setting")
        values[key] = expected
    return values


def config_bytes(values):
    return "".join(f"{key} {values[key]}\n" for key in sorted(values)).encode()


def safe_name(name):
    path = PurePosixPath(name)
    return (bool(name) and not path.is_absolute() and ".." not in path.parts
            and "\\" not in name and "\x00" not in name
            and all(ord(c) >= 32 for c in name))


def read_payload(path, expected):
    data = regular(path)
    if not re.fullmatch(r"[a-f0-9]{64}", expected or "") or digest(data) != expected:
        raise Invalid("installer_checksum_mismatch")
    from io import BytesIO
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            total = 0
            seen = set()
            for member in archive.infolist():
                mode = member.external_attr >> 16
                if (not safe_name(member.filename) or member.filename in seen
                        or stat.S_ISLNK(mode) or member.flag_bits & 1
                        or stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR)):
                    raise Invalid("unsafe_archive_member")
                seen.add(member.filename)
                total += member.file_size
            if total > MAX_ARCHIVE or len(seen) > 1000:
                raise Invalid("expanded_archive_too_large")
            files = {name: archive.read("LTechAgent/data/" + name) for name in PAYLOAD}
    except (zipfile.BadZipFile, KeyError, RuntimeError, NotImplementedError):
        raise Invalid("installer_layout_invalid") from None
    for name in PAYLOAD[:3]:
        blob = files[name]
        # ELF64, little endian, ELF version 1, x86-64 machine, correct object type.
        elf_type = 3 if name == "libltech.so" else 2
        if (len(blob) < 64 or blob[:7] != b"\x7fELF\x02\x01\x01"
                or int.from_bytes(blob[18:20], "little") != 62
                or int.from_bytes(blob[16:18], "little") not in (elf_type, 3)):
            raise Invalid("installer_requires_linux_amd64_elf")
    return files


class StateLock:
    def __init__(self, root):
        self.root = root
        self.fd = None

    def __enter__(self):
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.root.is_symlink() or self.root.stat().st_uid != os.geteuid():
            raise Invalid("state_ownership_invalid")
        self.root.chmod(0o700)
        self.fd = os.open(self.root / LOCK, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(self.fd)
            self.fd = None
            raise Invalid("state_already_in_use") from None
        return self

    def __exit__(self, *_):
        if self.fd is not None:
            os.close(self.fd)


def instance_id():
    try:
        return str(uuid.UUID(os.environ["AGENT_INSTANCE_ID"]))
    except (ValueError, KeyError):
        raise Invalid("unique_agent_instance_uuid_required") from None


def metadata(root, identity):
    if (root / TRANSACTION).exists():
        raise Invalid("interrupted_transaction_restore_required")
    try:
        meta = json.loads(regular(root / META, 65536))
        if meta["schema"] != 1 or meta["instance_id"] != identity:
            raise Invalid("state_identity_or_schema_mismatch")
        for name, expected in meta["payload"].items():
            if name not in PAYLOAD or digest(regular(root / name)) != expected:
                raise Invalid("payload_changed_explicit_upgrade_or_restore_required")
        if set(meta["payload"]) != set(PAYLOAD):
            raise Invalid("state_metadata_invalid")
    except (ValueError, KeyError, TypeError, AttributeError):
        raise Invalid("state_metadata_invalid") from None
    return meta


def prepare(root, identity, files, values, archive_hash, upgrade=False):
    canonical = config_bytes(values)
    if (root / META).exists():
        meta = metadata(root, identity)
        if not upgrade:
            if meta["installer_sha256"] != archive_hash or meta["config_sha256"] != digest(canonical):
                raise Invalid("inputs_changed_explicit_upgrade_required")
            # Reassert TLS/update policy on each start, preserving agent identity.
            atomic(root / "agent_config", canonical)
            return False
        if meta["registration_target"] != digest((values["server_url"] + "\n" + values["location_id"]).encode()):
            raise Invalid("registration_target_change_requires_separate_identity")
    elif any(p.name != LOCK for p in root.iterdir()):
        raise Invalid("partial_or_unmanaged_state_refused")
    elif upgrade:
        raise Invalid("upgrade_requires_initialized_state")
    atomic(root / TRANSACTION, b"restore snapshot after interrupted operation\n")
    for name, data in files.items():
        atomic(root / name, data)
        (root / name).chmod(0o500)
    atomic(root / "agent_config", canonical)
    json_write(root / META, {
        "schema": 1, "instance_id": identity,
        "installer_sha256": archive_hash,
        "config_sha256": digest(canonical),
        "registration_target": digest((values["server_url"] + "\n" + values["location_id"]).encode()),
        "payload": {name: digest(data) for name, data in files.items()},
    })
    (root / TRANSACTION).unlink()
    return True


def backup(root, destination, identity):
    metadata(root, identity)
    destination = Path(destination)
    checksum = Path(str(destination) + ".sha256")
    if destination.exists() or destination.is_symlink() or checksum.exists() or checksum.is_symlink():
        raise Invalid("backup_destination_exists")
    with tarfile.open(destination, "x") as archive:
        for path in sorted(root.rglob("*")):
            if path.name == LOCK:
                continue
            if path.is_symlink() or not (path.is_file() or path.is_dir()):
                raise Invalid("unsupported_state_file_type")
            archive.add(path, arcname=str(path.relative_to(root)), recursive=False)
    destination.chmod(0o600)
    with destination.open("rb") as stream:
        value = hashlib.file_digest(stream, "sha256").hexdigest()
    atomic(str(destination) + ".sha256", (value + "\n").encode())


def restore(root, source, identity):
    source = Path(source)
    expected = regular(str(source) + ".sha256", 128).decode().strip()
    if source.is_symlink() or not source.is_file() or source.stat().st_size > MAX_SNAPSHOT:
        raise Invalid("snapshot_file_invalid")
    with source.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha256").hexdigest()
    if actual != expected:
        raise Invalid("snapshot_checksum_mismatch")
    # Stage on the state volume, not in the small /tmp tmpfs. Retain the lock.
    with tempfile.TemporaryDirectory(prefix=".wrapper-restore-", dir=root) as temporary:
        stage = Path(temporary)
        with tarfile.open(source, mode="r:") as archive:
            members = archive.getmembers()
            names = set()
            if sum(m.size for m in members) > MAX_SNAPSHOT or len(members) > 10000:
                raise Invalid("snapshot_too_large")
            for member in members:
                if (not safe_name(member.name) or member.name in names
                        or not (member.isfile() or member.isdir()) or member.name == LOCK):
                    raise Invalid("unsafe_snapshot_member")
                names.add(member.name)
                target = stage / member.name
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True, mode=0o700)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                    with archive.extractfile(member) as stream, target.open("xb") as output:
                        shutil.copyfileobj(stream, output, length=65536)
                        output.flush()
                        os.fsync(output.fileno())
                    target.chmod(0o500 if member.name in PAYLOAD else 0o600)
        metadata(stage, identity)
        atomic(root / TRANSACTION, b"restore incomplete\n")
        for path in root.iterdir():
            if path.name not in (LOCK, TRANSACTION, stage.name):
                if path.is_dir() and not path.is_symlink():
                    shutil.rmtree(path)
                else:
                    path.unlink()
        for path in stage.iterdir():
            target = root / path.name
            if path.is_dir():
                shutil.copytree(path, target)
            else:
                shutil.copy2(path, target)
        (root / TRANSACTION).unlink()


def process_info(pid):
    data = Path(f"/proc/{int(pid)}/stat").read_text().rpartition(") ")[2].split()
    return data[0], data[19]


def health(root=STATE, status=STATUS):
    result = {"process": "unhealthy", "communication": "unknown", "host_accuracy": "unverified"}
    try:
        data = json.loads(regular(status, 8192))
        if time.monotonic() - data["checked_at"] > 10:
            return result
        for key in ("child", "supervisor"):
            state, start = process_info(data[key]["pid"])
            if state in ("Z", "T", "t", "X") or start != data[key]["start"]:
                return result
        if not os.access(root, os.R_OK | os.W_OK | os.X_OK) or (root / TRANSACTION).exists():
            return result
        with open(root / LOCK, "rb") as stream:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return result
            except BlockingIOError:
                pass
        result["process"] = "healthy"
    except (OSError, ValueError, KeyError, IndexError, TypeError, Invalid):
        pass
    return result


def rotate(path, limit=LOG_LIMIT):
    if not path.is_file() or path.is_symlink() or path.stat().st_size < limit:
        return
    for index in (2, 1):
        old = Path(str(path) + f".{index}")
        if old.is_file() and not old.is_symlink():
            os.replace(old, str(path) + f".{index + 1}")
    with path.open("rb") as stream:
        stream.seek(-limit, os.SEEK_END)
        atomic(str(path) + ".1", stream.read())
    # Copy-truncate preserves vendor open descriptors; diagnostics may lose a race.
    with path.open("r+b") as stream:
        stream.truncate(0)
    path.chmod(0o600)


def redact(text, secrets):
    for secret in sorted(set(secrets), key=len, reverse=True):
        if secret:
            text = text.replace(secret, "[REDACTED]")
    return re.sub(r"(?i)((?:password|passkey|token|secret|authorization)\s*[:= ]\s*)[^\s,;]+",
                  r"\1[REDACTED]", text)


def supervise(root, values, shutdown_seconds):
    """One child, one lifetime lock; Docker owns bounded crash restarts."""
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    child = subprocess.Popen([str(root / "ltechagent")], cwd=root,
                             stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, start_new_session=True)
    stopping = None

    def stop(signum, _frame):
        nonlocal stopping
        if stopping is None:
            stopping = time.monotonic()
            event("stopping", signal=signum)
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    selector = selectors.DefaultSelector()
    selector.register(child.stdout, selectors.EVENT_READ)
    os.set_blocking(child.stdout.fileno(), False)
    secrets = {values["system_password"], values["server_url"]}
    pending = ""
    capture = root / "wrapper-capture.log"
    event("agent_started", pid=child.pid, communication="unknown", host_accuracy="unverified")
    try:
        while child.poll() is None:
            if stopping is not None and time.monotonic() - stopping >= shutdown_seconds:
                event("shutdown_deadline_exceeded")
                os.killpg(child.pid, signal.SIGKILL)
                break
            for _key, _events in selector.select(timeout=0.5):
                chunk = child.stdout.read(65536)
                if chunk:
                    pending += chunk.decode("utf-8", errors="replace")
                    if "\n" in pending:
                        complete, _, pending = pending.rpartition("\n")
                        with capture.open("a", encoding="utf-8") as stream:
                            stream.write(redact(complete, secrets) + "\n")
                    if len(pending) > 65536:
                        pending = ""  # Discard oversized records instead of partial secret output.
                elif chunk == b"":
                    selector.unregister(child.stdout)
            # Never export native logs. Bound known vendor log files privately.
            for path in root.iterdir():
                if path.name.endswith((".log", ".debug")):
                    rotate(path)
            for name in ("state", "state.old"):
                path = root / name
                if path.is_file() and not path.is_symlink() and path.stat().st_size < 1048576:
                    try:
                        state_data = json.loads(path.read_bytes())
                        for key, value in state_data.items():
                            if re.search("password|passkey|token|secret", key, re.I) and isinstance(value, str):
                                secrets.add(value)
                    except (ValueError, AttributeError):
                        pass
            try:
                json_write(STATUS, {"checked_at": time.monotonic(),
                           "child": {"pid": child.pid, "start": process_info(child.pid)[1]},
                           "supervisor": {"pid": os.getpid(), "start": process_info(os.getpid())[1]}})
            except FileNotFoundError:
                pass
        code = child.wait(timeout=5)
    finally:
        STATUS.unlink(missing_ok=True)
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        child.wait(timeout=5)
        selector.close()
        child.stdout.close()
    event("agent_exited", code=code)
    return code if code >= 0 else 128 - code


def main(argv=None):
    parser = argparse.ArgumentParser(description="Experimental Automate wrapper")
    parser.add_argument("command", choices=("run", "init", "upgrade", "backup", "restore"))
    args = parser.parse_args(argv)
    os.umask(0o077)
    try:
        if os.environ.get("ACCEPT_EXPERIMENTAL") != "yes":
            raise Invalid("explicit_experimental_opt_in_required")
        if platform.machine() not in ("x86_64", "AMD64"):
            raise Invalid("linux_amd64_required")
        identity = instance_id()
        with StateLock(STATE):
            if args.command == "backup":
                backup(STATE, "/backup/snapshot.tar", identity)
                event("backup_complete")
                return 0
            if args.command == "restore":
                restore(STATE, "/backup/snapshot.tar", identity)
                event("restore_complete")
                return 0
            archive_hash = os.environ.get("INSTALLER_SHA256", "")
            files = read_payload(os.environ.get("INSTALLER_FILE", "/run/secrets/installer.zip"), archive_hash)
            values = config(regular(os.environ.get("AGENT_CONFIG_FILE", "/run/secrets/agent_config"), 65536))
            changed = prepare(STATE, identity, files, values, archive_hash, args.command == "upgrade")
            event("payload_prepared" if changed else "identity_reused")
            if args.command != "run":
                return 0
            seconds = int(os.environ.get("SHUTDOWN_SECONDS", "60"))
            if not 1 <= seconds <= 3600:
                raise Invalid("shutdown_timeout_invalid")
            # Only transient local process-launch errors retry. Never rerun enrollment.
            for attempt in range(4):
                try:
                    return supervise(STATE, values, seconds)
                except BlockingIOError:
                    if attempt == 3:
                        raise
                    event("launch_retry", attempt=attempt + 1)
                    time.sleep(2 ** attempt)
    except Invalid as exc:
        event("refused", reason=str(exc))
        return 78
    except (OSError, ValueError, tarfile.TarError, zipfile.BadZipFile):
        event("failed", reason="local_operation_failed_no_sensitive_details_logged")
        return 70
    return 70
