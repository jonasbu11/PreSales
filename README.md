# PreSales

For presales stuff.

## Skills

- `skills/loe`: Level of Effort workbook builder.
- `skills/strip`: de-identify client or engagement material before any of it leaves for an outside model. Reads its rules and calibration gate from the strip-kit function.
- `skills/strip-lab`: calibrate those rules with invented fixtures and re-identification trials on Bedrock. Opens or closes the gate `strip` checks.

## strip-kit

`strip-kit/` is the backend the two strip skills call: one Lambda, one DynamoDB table, Bedrock as the adversary. Deploy once per AWS account with SAM, seed once, then each user points their AWS connector at that account. Deploy, seed and first-run steps are in `strip-kit/README.md`.

Users: [@mkohn](https://github.com/mkohn) and [@josephvarghese-svg](https://github.com/josephvarghese-svg) run strip-kit in their own AWS accounts. Changes to `template.yaml`, the handler's action contract or the seed shape affect their deployments; see [CHANGELOG.md](CHANGELOG.md) before upgrading.

Security: vulnerability reports go through private reporting, not issues. Threat model, scope and response times are in [SECURITY.md](SECURITY.md).
