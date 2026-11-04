# PreSales

For presales stuff.

## Skills

- `skills/loe`: Level of Effort workbook builder.
- `skills/strip`: de-identify client or engagement material before any of it leaves for an outside model. Reads its rules and calibration gate from the strip-kit function.
- `skills/strip-lab`: calibrate those rules with invented fixtures and re-identification trials on Bedrock. Opens or closes the gate `strip` checks.

## strip-kit

`strip-kit/` is the backend the two strip skills call: one Lambda, one DynamoDB table, Bedrock as the adversary. Deploy once per AWS account with SAM, seed once, then each user points their AWS connector at that account. Deploy, seed and first-run steps are in `strip-kit/README.md`.

Security: vulnerability reports go through private reporting, not issues. Threat model, scope and response times are in [SECURITY.md](SECURITY.md).
