# Compatibility evidence

Only completed tests belong in this table; see [the validation record](validation.md).

| Combination | Evidence level |
| --- | --- |
| Ubuntu 24.04 amd64 runtime + original synthetic ELF fixture, local Docker 29.8.1 | Unit and Docker integration tests; wrapper behavior only. |

Ubuntu 24.04 amd64 **host with the real Automate agent** is the first planned
target, not a verified combination. No real agent runtime, Ubuntu host release,
Automate server version, ARM architecture or 32-bit image is certified by this
project. The inspected x86-64 ELF architecture and glibc references are static
evidence, not runtime compatibility results. Docker Compose 5.5.1 is the local
validation version; older Compose versions require their own checks.
