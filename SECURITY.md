# Security Policy

## Security maintainer

[Jonas Bull] ([@jonasbu11](https://github.com/jonasbu11)) is the sole
security maintainer for this project and handles all reports directly.

## Supported versions

Only the latest release receives security fixes.

| Version | Supported |
| ------- | --------- |
| latest  | yes       |
| older   | no        |

## Reporting a vulnerability

Please report privately, not in a public issue:

- Preferred: **GitHub private vulnerability reporting** on this repo
  (Security tab → Report a vulnerability)
- Or email: [jb@jonasbull.com]

Include the version, a description of the issue, reproduction steps or a
proof of concept, and the impact you believe it has.

## What to expect

- Acknowledgement within [3] business days
- An initial assessment within [7] business days
- Fix or mitigation timeline once the issue is confirmed

This is a small project maintained by one person, so these are best-effort
targets rather than contractual SLAs.

## Disclosure

Coordinated disclosure. Once a fix is available I'll publish an advisory
and credit you by name or handle, whichever you prefer. If the issue
warrants it, I'll request a CVE through the GitHub CNA.

If you get no response after [14] days and have chased once, you're free to
disclose publicly.

## Credit

Reporters are credited in the advisory and release notes unless they ask
not to be.

## Scope

In scope: the code in this repository and its published release artifacts.

Out of scope:
- Issues in third-party dependencies (report those upstream)
- [Your hosted instance / demo, if any]
- Missing hardening headers with no demonstrable impact
- Automated scanner output with no reproduction

## Safe harbour

Good-faith testing against this project's own code and a locally-run copy
is authorised. Don't touch other people's deployments or data.
