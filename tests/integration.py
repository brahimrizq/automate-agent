"""Docker integration tests use only original synthetic ELF fixtures."""
import json
import os
from pathlib import Path
import subprocess
import time
import unittest
import uuid

IMAGE = os.environ.get("MOCK_IMAGE", "automate-agent:mock")
RUNTIME = os.environ.get("RUNTIME_IMAGE", "automate-agent:local")


def docker(*args, check=True):
    result = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=120)
    if check and result.returncode:
        raise AssertionError(f"docker command failed ({args[0]}): {result.stderr}\n{result.stdout}")
    return result.stdout.strip() if check else result


class Integration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.archive_hash = docker("run", "--rm", "--network", "none", "--entrypoint", "python3", IMAGE,
                                  "-c", "import hashlib; print(hashlib.sha256(open('/fixtures/installer.zip','rb').read()).hexdigest())")

    def setUp(self):
        self.prefix = "automate-test-" + uuid.uuid4().hex[:12]
        self.identity = str(uuid.uuid4())
        self.containers = []
        self.volumes = []
        self.networks = []
        self.volume = self.new_volume()

    def tearDown(self):
        for name in self.containers:
            docker("rm", "-f", name, check=False)
        for name in self.volumes:
            docker("volume", "rm", name, check=False)
        for name in self.networks:
            docker("network", "rm", name, check=False)

    def new_volume(self):
        name = self.prefix + "-v" + str(len(self.volumes))
        docker("volume", "create", name)
        self.volumes.append(name)
        return name

    def start(self, *, volume=None, identity=None, options=(), command="run"):
        name = self.prefix + "-c" + str(len(self.containers))
        self.containers.append(name)
        docker("run", "-d", "--name", name, "--read-only", "--cap-drop", "ALL",
               "--security-opt", "no-new-privileges", "--memory", "512m", "--cpus", "1", "--pids-limit", "256",
               "--tmpfs", "/run/wrapper:rw,nosuid,nodev,noexec,size=8m,mode=0700",
               "--tmpfs", "/tmp:rw,nosuid,nodev,noexec,size=64m",
               "--mount", f"type=volume,source={volume or self.volume},target=/usr/local/ltechagent",
               "-e", "ACCEPT_EXPERIMENTAL=yes", "-e", "SHUTDOWN_SECONDS=5",
               "-e", f"AGENT_INSTANCE_ID={identity or self.identity}",
               "-e", f"INSTALLER_SHA256={self.archive_hash}", *options, IMAGE, command)
        return name

    def until(self, callback, timeout=20):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                value = callback()
                if value:
                    return value
            except (AssertionError, ValueError, KeyError):
                pass
            time.sleep(0.25)
        self.fail("timed out waiting for synthetic fixture")

    def read(self, name, path):
        return docker("exec", name, "cat", "/usr/local/ltechagent/" + path)

    def healthy(self, name):
        result = docker("exec", name, "python3", "/opt/wrapper/healthcheck.py", check=False)
        return result.returncode == 0

    def wait_exit(self, name):
        return int(docker("wait", name))

    def test_initialization_recreation_and_graceful_shutdown(self):
        first = self.start(options=("--network", "none"))
        self.until(lambda: self.healthy(first))
        state = self.read(first, "state")
        status = json.loads(docker("exec", first, "python3", "/opt/wrapper/healthcheck.py"))
        self.assertEqual(status["communication"], "unknown")
        docker("stop", "-t", "10", first)
        self.assertEqual(self.wait_exit(first), 0)
        second = self.start(options=("--network", "none"))
        self.until(lambda: self.healthy(second))
        self.assertEqual(state, self.read(second, "state"))
        self.assertEqual(self.read(second, "mock-registrations"), "1")
        self.assertEqual(self.read(second, "mock-stopped"), "graceful")

    def test_separate_volumes_get_distinct_identities(self):
        one = self.start(options=("--network", "none"))
        two = self.start(volume=self.new_volume(), identity=str(uuid.uuid4()), options=("--network", "none"))
        self.until(lambda: self.healthy(one) and self.healthy(two))
        self.assertNotEqual(self.read(one, "state"), self.read(two, "state"))

    def test_concurrent_volume_refused(self):
        first = self.start(options=("--network", "none"))
        self.until(lambda: self.healthy(first))
        second = self.start(options=("--network", "none"))
        self.assertEqual(self.wait_exit(second), 78)
        self.assertIn("state_already_in_use", docker("logs", second))

    def test_agent_crash_is_propagated_and_restart_recovers(self):
        first = self.start(options=("--network", "none", "-e", "MOCK_MODE=crash"))
        self.assertEqual(self.wait_exit(first), 42)
        second = self.start(options=("--network", "none"))
        self.until(lambda: self.healthy(second))
        self.assertEqual(self.read(second, "mock-registrations"), "1")

    def test_stopped_live_process_is_unhealthy_and_recovers(self):
        name = self.start(options=("--network", "none"))
        self.until(lambda: self.healthy(name))
        pid = json.loads(docker("exec", name, "cat", "/run/wrapper/status.json"))["child"]["pid"]
        docker("exec", name, "kill", "-STOP", str(pid))
        self.assertFalse(self.healthy(name))
        docker("exec", name, "kill", "-CONT", str(pid))
        self.until(lambda: self.healthy(name))

    def test_missing_installer_and_bad_hash_refused(self):
        for variable in ["INSTALLER_FILE=/missing", "INSTALLER_SHA256=" + "0" * 64]:
            name = self.start(volume=self.new_volume(), options=("--network", "none", "-e", variable))
            self.assertEqual(self.wait_exit(name), 78)

    def test_docker_crash_restart_budget_is_bounded(self):
        name = self.start(options=("--network", "none", "--restart", "on-failure:2", "-e", "MOCK_MODE=crash"))
        def exhausted():
            state = json.loads(docker("inspect", name))[0]
            return state["RestartCount"] == 2 and state["State"]["Status"] == "exited"
        self.until(exhausted)
        self.assertEqual(self.wait_exit(name), 42)
        recovered = self.start(options=("--network", "none"))
        self.until(lambda: self.healthy(recovered))
        self.assertEqual(self.read(recovered, "mock-registrations"), "1")

    def test_container_backup_upgrade_and_restore_preserve_identity(self):
        name = self.start(options=("--network", "none"))
        self.until(lambda: self.healthy(name))
        state = self.read(name, "state")
        docker("stop", "-t", "10", name)
        # Backups stay on a disposable Docker volume; no host ownership changes.
        backup_volume = self.new_volume()
        options = ("--network", "none", "--mount", f"type=volume,source={backup_volume},target=/backup")
        snapshot = self.start(options=options, command="backup")
        self.assertEqual(self.wait_exit(snapshot), 0)
        upgrade = self.start(options=("--network", "none"), command="upgrade")
        self.assertEqual(self.wait_exit(upgrade), 0)
        rollback = self.start(options=options, command="restore")
        self.assertEqual(self.wait_exit(rollback), 0)
        resumed = self.start(options=("--network", "none"))
        self.until(lambda: self.healthy(resumed))
        self.assertEqual(self.read(resumed, "state"), state)

    def test_init_never_executes_agent(self):
        initialized = self.start(options=("--network", "none"), command="init")
        self.assertEqual(self.wait_exit(initialized), 0)
        result = docker("run", "--rm", "--network", "none", "--mount",
                        f"type=volume,source={self.volume},target=/check,readonly",
                        "--entrypoint", "python3", RUNTIME, "-c",
                        "from pathlib import Path; assert not Path('/check/state').exists(); assert Path('/check/.wrapper.json').exists()")
        self.assertEqual(result, "")

    def test_network_and_dns_failure_recovery_keep_identity(self):
        network = self.prefix + "-net"
        docker("network", "create", "--internal", network)
        self.networks.append(network)
        name = self.start(options=("--network", network, "-e", "MOCK_HOST=sink"))
        self.until(lambda: self.read(name, "mock-network") == "offline")
        identity = self.read(name, "state")
        sink = self.prefix + "-sink"
        self.containers.append(sink)
        server = "import socket; s=socket.socket(); s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1); s.bind(('0.0.0.0',8080)); s.listen(); exec('while True:\\n c,a=s.accept(); c.close()')"
        docker("run", "-d", "--name", sink, "--network", network, "--network-alias", "sink",
               "--read-only", "--cap-drop", "ALL", "--entrypoint", "python3", RUNTIME, "-c", server)
        self.until(lambda: self.read(name, "mock-network") == "online")
        docker("network", "disconnect", network, sink)
        self.until(lambda: self.read(name, "mock-network") == "offline")
        docker("network", "connect", "--alias", "sink", network, sink)
        self.until(lambda: self.read(name, "mock-network") == "online")
        self.assertEqual(identity, self.read(name, "state"))
        self.assertTrue(self.healthy(name))

    def test_log_growth_is_bounded_and_capture_is_redacted(self):
        name = self.start(options=("--network", "none", "-e", "MOCK_MODE=logs"))
        self.until(lambda: self.healthy(name))
        self.until(lambda: docker("exec", name, "test", "-f", "/usr/local/ltechagent/agent.log.1", check=False).returncode == 0)
        capture = self.read(name, "wrapper-capture.log")
        self.assertNotIn("synthetic-enrollment", capture)
        self.assertNotIn("synthetic-enrollment", docker("logs", name))
        stats = json.loads(docker("exec", name, "python3", "-c",
                                  "import pathlib,json; print(json.dumps({p.name:p.stat().st_size for p in pathlib.Path('.').glob('agent.log*')}))"))
        self.assertLessEqual(len(stats), 4)
        self.assertLess(max(stats.values()), 15 * 1024 * 1024)

    def test_public_image_has_no_agent_payload_or_java(self):
        script = "from pathlib import Path; assert not list(Path('/usr/local/ltechagent').iterdir()); assert not Path('/fixtures').exists(); assert not Path('/usr/bin/java').exists()"
        docker("run", "--rm", "--network", "none", "--entrypoint", "python3", RUNTIME, "-c", script)


if __name__ == "__main__":
    unittest.main(verbosity=2)
