# Contributing

Discuss behavior changes in an issue without customer data. Fork, create a
branch, make focused changes and run `scripts/check.sh`. The host needs existing
Docker/Compose, Bash, Git and Python; compilers and linters run in containers.

Use original synthetic fixtures only. Do not commit vendor software, real
archives, tenant identifiers, credentials, private certificates or registered
state. Keep secrets outside the checkout and review the entire staged diff.
Public PRs must not require production credentials or real-agent registration.

Document evidence separately from assumptions. Changes to host access, identity,
update handling or supported combinations require targeted tests. A mock result
must never be relabeled as a real-agent test. Update CHANGELOG.md and relevant
operator docs when changing behavior. Check action/tool pins against upstream
repositories and retain minimum workflow permissions.

Run a redacted Gitleaks scan over files and all Git history before publishing.
Submit a pull request to `main`; CI must pass. Original contributions are under
the repository MIT license. See SECURITY.md for private vulnerability reports.
