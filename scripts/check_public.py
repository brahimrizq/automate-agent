#!/usr/bin/env python3
"""Fail if tracked artifacts contain installer payloads or private file types."""
from pathlib import Path
import re
import subprocess
import sys

paths = subprocess.check_output(["git", "ls-files", "-z"]).decode().split("\0")
errors = []
for name in filter(None, paths):
    path = Path(name)
    if path.is_symlink():
        errors.append(name)
        continue
    forbidden = (path.suffix.lower() in {".zip", ".tar", ".tgz", ".so", ".pem", ".key", ".p12"}
                 or path.name in {"state", "agent_config", "ltechagent", "ltupdate", "template_bytes", ".env"}
                 or any(part in {"private", "backups", "artifacts"} for part in path.parts))
    data = path.read_bytes()
    if forbidden or data.startswith((b"\x7fELF", b"PK\x03\x04", b"\x1f\x8b")) or b"\x00" in data:
        errors.append(name)
    if path.suffix in {".yml", ".yaml"} and ".github/workflows/" in name:
        for action in re.findall(r"uses:\s*([^\s]+)", data.decode()):
            if not re.fullmatch(r"[^@]+@[a-f0-9]{40}", action):
                errors.append(name + ": unpinned action")
if errors:
    print("Public artifact audit failed:", *errors, sep="\n", file=sys.stderr)
    sys.exit(1)
print(f"Public artifact audit passed: {len(list(filter(None, paths)))} tracked text files")
