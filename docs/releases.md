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

## Consumer verification

Copy the exact digest from the GitHub release and substitute it below:

```sh
cosign verify \
  --certificate-identity 'https://github.com/brahimrizq/automate-agent/.github/workflows/release.yaml@refs/tags/v0.1.0-alpha.1' \
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
