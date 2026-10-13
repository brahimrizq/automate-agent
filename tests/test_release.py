"""Release gates use synthetic Git/API responses; these tests never push tags."""
import contextlib
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import release as r


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.version = "v0.1.0-alpha.3"
        self.sha = "a" * 40
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "CHANGELOG.md").write_text("## 0.1.0-alpha.3 — 2026-10-13\n")
        self.responses = {
            ("branch", "--show-current"): "main",
            ("status", "--porcelain"): "",
            ("remote", "get-url", "origin"): r.URL + ".git",
            ("remote", "get-url", "--push", "origin"): r.URL + ".git",
            ("rev-parse", "HEAD"): self.sha,
            ("ls-remote", "--exit-code", "origin", "refs/heads/main"): self.sha + "\trefs/heads/main",
            ("tag", "--list", self.version): "",
            ("ls-remote", "--tags", "origin", "refs/tags/" + self.version): "",
        }
        self.run = {"id": 1, "head_sha": self.sha, "head_branch": "main", "event": "push",
                    "status": "completed", "conclusion": "success", "html_url": r.URL + "/actions/runs/1"}
        self.runs = [self.run]
        self.existing_release = None
        self.git = self.enterContext(patch.object(r, "git", side_effect=lambda *args: self.responses[args]))
        self.api = self.enterContext(patch.object(r, "api", side_effect=self.api_response))
        self.enterContext(patch.object(r, "ROOT", self.root))
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))

    def api_response(self, path, **_kwargs):
        if path.startswith("releases/tags/"):
            return self.existing_release
        return {"workflow_runs": self.runs}

    def test_valid_prereleases(self):
        for version in (self.version, "v1.2.3-beta.1", "v1.0.0-rc.0"):
            with self.subTest(version=version), patch.dict(os.environ, VERSION=version):
                self.assertEqual(r.version_value(), version)

    def test_invalid_and_stable_versions(self):
        for version in ("", "v1.0.0", "v01.0.0-alpha.1", "v1.0.0-alpha.01",
                        "1.0.0-rc.1", "v1.0.0-dev.1", "v1.0.0-alpha.1; touch /tmp/no"):
            with self.subTest(version=version), patch.dict(os.environ, VERSION=version):
                with self.assertRaises(r.Refused):
                    r.version_value()

    def test_check_passes_without_mutating_git(self):
        self.assertEqual(r.preflight(self.version), self.sha)
        self.assertFalse(any(call.args[0] == "push" or call.args[:2] == ("tag", "-a")
                             for call in self.git.call_args_list))

    def test_git_preconditions_refuse_publication(self):
        failures = {
            ("branch", "--show-current"): "feature",
            ("status", "--porcelain"): "?? private-file",
            ("remote", "get-url", "origin"): "https://github.com/example/fork.git",
            ("remote", "get-url", "--push", "origin"): "https://github.com/example/fork.git",
            ("ls-remote", "--exit-code", "origin", "refs/heads/main"): "b" * 40 + "\trefs/heads/main",
            ("tag", "--list", self.version): self.version,
            ("ls-remote", "--tags", "origin", "refs/tags/" + self.version): self.sha,
        }
        for command, response in failures.items():
            with self.subTest(command=command), patch.dict(self.responses, {command: response}):
                with self.assertRaises(r.Refused):
                    r.publish(self.version)

    def test_existing_github_release_refused(self):
        self.existing_release = {"html_url": r.URL + "/releases/tag/" + self.version}
        with self.assertRaisesRegex(r.Refused, "GitHub release already"):
            r.publish(self.version)

    def test_changelog_requires_exact_version(self):
        (self.root / "CHANGELOG.md").write_text("## 0.1.0-alpha.30\n")
        with self.assertRaisesRegex(r.Refused, "CHANGELOG"):
            r.publish(self.version)

    def test_missing_or_wrong_commit_ci_refused(self):
        for runs in ([], [dict(self.run, head_sha="b" * 40)],
                     [dict(self.run, head_branch="feature")], [dict(self.run, event="pull_request")]):
            self.runs = runs
            with self.subTest(runs=runs), self.assertRaises(r.Refused):
                r.publish(self.version)

    def test_latest_ci_must_be_successful_and_complete(self):
        for status, conclusion in (("in_progress", None), ("completed", "failure"),
                                   ("completed", "cancelled")):
            self.runs = [self.run, dict(self.run, id=2, status=status, conclusion=conclusion)]
            with self.subTest(status=status, conclusion=conclusion), self.assertRaises(r.Refused):
                r.publish(self.version)

    def test_publish_uses_exact_checked_commit_and_explicit_tag_ref(self):
        tag = ("tag", "-a", self.version, self.sha, "-m", "Experimental Automate wrapper " + self.version)
        push = ("push", "origin", f"refs/tags/{self.version}:refs/tags/{self.version}")
        self.responses.update({tag: "", push: ""})
        r.publish(self.version)
        self.assertEqual(self.git.call_args_list[-2].args, tag)
        self.assertEqual(self.git.call_args_list[-1].args, push)

    def test_failed_push_retains_tag_and_never_force_pushes(self):
        with patch.object(r, "preflight", return_value=self.sha), \
                patch.object(r, "git", side_effect=["", r.Refused("push failed")]) as git:
            with self.assertRaisesRegex(r.Refused, "local tag was retained"):
                r.publish(self.version)
            self.assertEqual(git.call_count, 2)
            self.assertNotIn("--force", git.call_args.args)

    def test_status_does_not_modify_git(self):
        self.runs = [dict(self.run, head_branch=self.version)]
        r.status(self.version)
        self.git.assert_not_called()

    def test_api_failure_cannot_authorize_release(self):
        self.api.side_effect = r.Refused("GitHub unavailable")
        with self.assertRaises(r.Refused):
            r.publish(self.version)
        self.assertFalse(any(call.args[0] == "push" for call in self.git.call_args_list))


class ApiTests(unittest.TestCase):
    def test_public_request_and_optional_token(self):
        for token in ("", "synthetic-github-token"):
            with patch.dict(os.environ, {"GH_TOKEN": token, "GITHUB_TOKEN": ""}), \
                    patch.object(r.urllib.request, "urlopen") as request:
                request.return_value.__enter__.return_value = io.BytesIO(b'{"workflow_runs": []}')
                self.assertEqual(r.api("actions/runs"), {"workflow_runs": []})
                headers = request.call_args.args[0].headers
                self.assertEqual(headers.get("Authorization"), "Bearer " + token if token else None)

    def test_api_404_is_only_allowed_when_requested(self):
        error = urllib.error.HTTPError("https://api.github.com", 404, "Not found", {}, None)
        with patch.object(r.urllib.request, "urlopen", side_effect=error):
            self.assertIsNone(r.api("releases/tags/v0.1.0-alpha.3", missing_ok=True))
            with self.assertRaises(r.Refused):
                r.api("actions/runs")

    def test_api_failure_does_not_expose_error_body(self):
        for error in (urllib.error.HTTPError("https://api.github.com", 403, "sensitive-body", {}, None),
                      urllib.error.URLError("sensitive-body"), TimeoutError("sensitive-body")):
            with self.subTest(error=type(error)), patch.object(r.urllib.request, "urlopen", side_effect=error):
                with self.assertRaises(r.Refused) as caught:
                    r.api("actions/runs")
                self.assertNotIn("sensitive-body", str(caught.exception))
