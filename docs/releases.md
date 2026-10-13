# Release and supply-chain policy

`CI` validates pushes, pull requests and a weekly rebuild. Untrusted pull
requests receive no production credentials or privileged self-hosted runner.
All action references are full upstream commit SHAs. Container lint/scanning
tools are digest pinned. Dependabot updates Dockerfile and action references;
maintainers also review script tool pins on each release. Release cache scope is
separate from pull request tests.

`Release` accepts semantic prerelease tags only. It verifies main ancestry and
passing main CI for that exact commit, builds only the `runtime` amd64 target,
scans it, publishes to GHCR, signs the image digest with keyless Cosign, and
attaches BuildKit plus GitHub provenance/SBOM attestations. The GitHub prerelease
is created only after signing and attestation steps succeed. Failed releases
must not silently move an existing version tag; investigate, then use a new
version if released content would change.

Package versions intentionally receive security updates during builds; the
base digest is pinned and the resulting release digest is immutable. Rebuilding
the same source at a later date need not produce identical bytes. Never replace
a published version tag or promote a scheduled rebuild directly to production.

## Maintainer commands

The Makefile uses existing GNU Make, Bash, Git, Python 3 and Docker/Compose.
Linters, scanners and compilers run in pinned containers. The release helper uses
Python's standard library and public GitHub API reads; GitHub CLI is not required.
Git must already be authenticated with permission to push a new tag to this
repository. Optional `GH_TOKEN` or `GITHUB_TOKEN` environment variables can raise
API rate limits; never put token values in the Makefile, command arguments or Git.

| Command | Action |
| --- | --- |
| `make help` | List all targets; plain `make` also shows help. |
| `make check` | Lint, validate Compose, build both targets, run all tests and audit tracked public files. |
| `make lint` / `make compose-check` | Run focused lint/configuration checks. |
| `make build` | Build only the public dependency runtime. |
| `make test` / `make unit` / `make integration` | Run all tests or a selected suite with synthetic inputs. |
| `make audit` | Inspect tracked public artifacts and action pins. |
| `make scan-secrets` | Redacted Gitleaks scan of all history and local files. |
| `make scan-image` | Build/export the dependency image and fail on HIGH/CRITICAL findings, including unfixed. |
| `make sbom` | Build/export the dependency image and write `artifacts/sbom.spdx.json`. |
| `make versions` | List local version tags; first use `git fetch --tags` to refresh them. |
| `make release-check VERSION=…` | Check readiness without creating or pushing a tag. |
| `make release VERSION=…` | Repeat the gates, create an annotated tag and push that exact tag. |
| `make release-status VERSION=…` | Read the release workflow result and published release URL. |

Image scans use an exported dependency image and a dedicated Trivy cache volume;
they do not mount the Docker socket into a scanner. Generated image archives and
SBOMs remain in ignored `artifacts/`. Local scans/SBOMs describe the local build;
GitHub independently scans and attests the image it publishes.

For example, to prepare `v0.1.0-alpha.3` (choose an unused version):

1. On a working branch, move the relevant `Unreleased` entries to a dated
   `## 0.1.0-alpha.3` changelog heading. Update affected documentation and review
   the complete diff. Run `make check`, `make scan-secrets`, `make scan-image`
   and optionally `make sbom`. Commit the reviewed changes and merge through a
   pull request after CI passes.
2. Update local main and wait for CI on the resulting main commit:

   ```sh
   git switch main
   git pull --ff-only origin main
   git fetch --tags origin
   make release-check VERSION=v0.1.0-alpha.3
   make release VERSION=v0.1.0-alpha.3
   make release-status VERSION=v0.1.0-alpha.3
   ```

Release gates require a clean tree on `main`, the expected origin fetch/push
URLs, HEAD equal to live remote main, an exact changelog entry, no existing
local/remote tag or GitHub release, and the latest push CI for that exact main
commit completed successfully. Only `alpha`, `beta` and `rc` semantic prereleases
are accepted. Check and status targets do not modify the repository.

`make release` returning successfully means the tag was pushed, not that the
image was published. Check the workflow URL, wait for its successful completion,
then verify the release image/signature/attestations below. No Makefile target
pushes an image directly or creates a stable release. A failed tag push retains
the local annotated tag: inspect the remote state and resolve authentication or
transport failures before any manual retry; never force-push. A failed workflow
must be investigated before choosing a new version for changed release content.

## Consumer verification

Copy the exact digest from the GitHub release and substitute it below:

```sh
cosign verify \
  --certificate-identity 'https://github.com/brahimrizq/automate-agent/.github/workflows/release.yaml@refs/tags/v0.1.0-alpha.2' \
  --certificate-oidc-issuer 'https://token.actions.githubusercontent.com' \
  'ghcr.io/brahimrizq/automate-agent@sha256:REPLACE_WITH_RELEASE_DIGEST'

gh attestation verify \
  'oci://ghcr.io/brahimrizq/automate-agent@sha256:REPLACE_WITH_RELEASE_DIGEST' \
  --repo brahimrizq/automate-agent
```

Verification tools are optional operator tools; this project never installs them
on the monitored host. Verify on an administrative workstation or isolated tool
container. Signatures identify the build source; they do not establish agent
support, security, or host accuracy.

Trivy gates HIGH/CRITICAL findings, including unfixed findings. There are no
vulnerability exceptions at inception. Any future exception must be a reviewed,
machine-readable record naming the CVE/package, rationale, owner and expiry;
CI must reject expired records. Do not add an unbounded ignore list or silently
switch to `ignore-unfixed` to make a release pass.

References: [Docker build secrets](https://docs.docker.com/build/building/secrets/),
[GitHub workflow security](https://docs.github.com/en/actions/reference/security/secure-use),
[artifact attestations](https://docs.github.com/en/actions/concepts/security/artifact-attestations),
[Cosign verification](https://docs.sigstore.dev/cosign/verifying/verify/).
