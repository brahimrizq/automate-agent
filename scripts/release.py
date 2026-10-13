#!/usr/bin/env python3
"""Maintainer release commands; publication itself remains in trusted GitHub CI."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
REPO = "brahimrizq/automate-agent"
URL = f"https://github.com/{REPO}"
REMOTES = {URL, URL + ".git", f"git@github.com:{REPO}.git",
           f"ssh://git@github.com/{REPO}.git"}
VERSION_PATTERN = r"v(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)-(?:alpha|beta|rc)\.(?:0|[1-9][0-9]*)"


class Refused(Exception):
    """An actionable release failure, without credential-bearing tool output."""


def git(*args):
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True,
                                       stderr=subprocess.PIPE).strip()
    except subprocess.CalledProcessError:
        raise Refused("Git operation failed. Check repository access and Git authentication.") from None


def api(path, missing_ok=False):
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(f"https://api.github.com/repos/{REPO}/{path}", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        if missing_ok and error.code == 404:
            return None
        raise Refused(f"GitHub API returned HTTP {error.code}; check access or API rate limits.") from None
    except (urllib.error.URLError, TimeoutError, ValueError):
        raise Refused("GitHub API unavailable; no release was authorized by this check.") from None


def version_value():
    version = os.environ.get("VERSION", "")
    if not re.fullmatch(VERSION_PATTERN, version):
        raise Refused("Set VERSION to a semantic prerelease, e.g. v0.1.0-alpha.3; stable releases remain blocked.")
    return version


def preflight(version):
    if git("branch", "--show-current") != "main":
        raise Refused("Switch to main after merging the release changes through a pull request.")
    if git("status", "--porcelain"):
        raise Refused("Working tree is not clean. Commit and merge all release changes first.")
    if (git("remote", "get-url", "origin") not in REMOTES
            or git("remote", "get-url", "--push", "origin") not in REMOTES):
        raise Refused(f"Both origin fetch and push URLs must refer to {REPO}.")
    sha = git("rev-parse", "HEAD")
    remote_main = git("ls-remote", "--exit-code", "origin", "refs/heads/main").split()
    if not remote_main or remote_main[0] != sha:
        raise Refused("Local main must equal current origin/main; fetch and fast-forward before release.")
    if (git("tag", "--list", version)
            or git("ls-remote", "--tags", "origin", f"refs/tags/{version}")):
        raise Refused("Version tag already exists locally or remotely. Never replace a release tag.")
    if api(f"releases/tags/{version}", missing_ok=True) is not None:
        raise Refused("A GitHub release already uses this version. Choose an unused version.")
    changelog = (ROOT / "CHANGELOG.md").read_text()
    if not re.search(rf"^## {re.escape(version[1:])}(?:\s|$)", changelog, re.MULTILINE):
        raise Refused("Add a dated CHANGELOG.md heading for this version and merge it before release.")
    query = urllib.parse.urlencode({"head_sha": sha, "event": "push", "per_page": 100})
    runs = api("actions/workflows/ci.yaml/runs?" + query)["workflow_runs"]
    matching = [run for run in runs if run["head_sha"] == sha and run["head_branch"] == "main"
                and run["event"] == "push"]
    latest = max(matching, key=lambda run: run["id"], default=None)
    if latest is None or latest["status"] != "completed" or latest["conclusion"] != "success":
        raise Refused(f"Latest main CI for this exact commit must succeed: {URL}/actions/workflows/ci.yaml")
    print(f"Release checks passed: {version} at {sha}\nCI: {latest['html_url']}")
    return sha


def publish(version):
    sha = preflight(version)
    # Pin the checked commit even if another local process changes HEAD.
    git("tag", "-a", version, sha, "-m", f"Experimental Automate wrapper {version}")
    try:
        git("push", "origin", f"refs/tags/{version}:refs/tags/{version}")
    except Refused:
        raise Refused("Tag push failed; the local tag was retained. Inspect local and remote tags before retrying; never force-push.") from None
    print(f"Pushed {version}; publication is pending GitHub Actions, not yet verified.\n"
          f"Run make release-status VERSION={version}\n{URL}/actions/workflows/release.yaml")


def status(version):
    query = urllib.parse.urlencode({"branch": version, "event": "push", "per_page": 100})
    runs = api("actions/workflows/release.yaml/runs?" + query)["workflow_runs"]
    matching = [run for run in runs if run["head_branch"] == version]
    latest = max(matching, key=lambda run: run["id"], default=None)
    if latest:
        print(f"Workflow: {latest['conclusion'] or latest['status']}\n{latest['html_url']}")
    else:
        print("No release workflow found yet for this version.")
    release = api(f"releases/tags/{version}", missing_ok=True)
    if release:
        print(f"Published release: {release['html_url']}")
    else:
        print("No published GitHub release found yet.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("check", "publish", "status"))
    args = parser.parse_args()
    try:
        version = version_value()
        {"check": preflight, "publish": publish, "status": status}[args.action](version)
    except (Refused, OSError) as error:
        message = str(error) if isinstance(error, Refused) else "Local operation failed; check files and installed tools."
        print("Release refused: " + message, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
