"""Build an original synthetic ZIP; never read a real installer."""
from pathlib import Path
import zipfile

root = Path(__file__).parent
with zipfile.ZipFile(root / "installer.zip", "w") as archive:
    for name in ("ltechagent", "libltech.so", "ltupdate"):
        archive.writestr("LTechAgent/data/" + name, (root / "ltechagent").read_bytes())
    archive.writestr("LTechAgent/data/uninstaller.sh", "#!/bin/sh\nexit 99\n")
    archive.writestr("LTechAgent/install.sh", "#!/bin/sh\nexit 99\n")
(root / "config").write_text(
    "server_url https://automate.example.invalid\n"
    "system_password synthetic-enrollment\nlocation_id 1\n")
