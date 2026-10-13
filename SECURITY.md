# Security policy

This project is experimental; there is no supported stable deployment yet.
Security fixes will target the latest prerelease. Vendor software remains under
ConnectWise's policies and is not redistributed here.

Public image vulnerability scans cover the dependency image only. They cannot
assess private vendor binaries, their bundled libraries, or later downloads.

Report wrapper vulnerabilities privately using
[GitHub private vulnerability reporting](https://github.com/brahimrizq/automate-agent/security/advisories/new).
Repository reporting was enabled and verified through GitHub's API on 2026-10-13.
Do not open public issues containing exploit details, customer addresses,
enrollment secrets, certificates, raw agent logs or registered state.

Include the wrapper commit/image digest, affected behavior and a synthetic
reproduction. Never attach a vendor archive. Maintainer: [Brahim Rizq](https://github.com/brahimrizq).
No response-time guarantee is implied.
