# Security Policy

## Security maintainer

Jonas Bull ([@jonasbu11](https://github.com/jonasbu11)) is the sole security
maintainer and handles all reports directly.

## What this project protects

`strip` removes client and engagement identifiers from material before any of
it is sent to an outside model. `strip-lab` calibrates those rules by running
re-identification trials on Bedrock, and `strip-kit` is the Lambda + DynamoDB
backend both skills call, deployed into the user's own AWS account via SAM.

The failure that matters is a **false negative**: an identifier survives
stripping and reaches a third-party model. Everything below follows from that.

## Threat model

In scope:
- Rules that miss an identifier class, or that a fixture can defeat
- Calibration gate logic that opens on too few or unrepresentative trials
- Over-broad IAM in the SAM template, or secrets/identifiers landing in logs
- DynamoDB storage of raw or insufficiently stripped material
- Injection through the material being stripped, reaching the rules engine
- Anything letting `strip` run against a stale or tampered rule set

Out of scope:
- Compromise of the host AWS account itself
- Third-party dependency bugs (report upstream)
- Missing hardening headers with no demonstrable impact
- Raw scanner output with no reproduction

## Reporting a vulnerability

Please report privately, not in a public issue:

- Preferred: **GitHub private vulnerability reporting** (Security tab →
  Report a vulnerability)
- Or email: jb@jonasbull.com

Include the commit or release tag, the identifier class or rule that fails, a
fixture that reproduces it, and the resulting leak.

## What to expect

Best-effort, sole maintainer: acknowledgement in 3 business days, initial
assessment in 7. Once confirmed, a fix or a documented mitigation.

## Disclosure

Coordinated. Fix first, then an advisory crediting you by name or handle,
whichever you prefer. If the issue warrants it, a CVE via the GitHub CNA.

No response after 14 days and one chase, and you're free to disclose.

## Scope of supported code

`main` and the latest tagged release only. Older commits and unmerged branches
get no fixes.

## Safe harbour

Good-faith testing against the code and your own local deploy is authorised.
Don't touch other people's AWS accounts or the client material in them.
