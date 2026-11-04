# Changelog

All notable changes to strip-kit and the strip skills. Versions are git tags; users deploying strip-kit should read the entry for every version between theirs and the one they are moving to.

## v0.1.1 (2026-11-03)

Security release. Advisory: [GHSA-q56c-76gq-653v](https://github.com/jonasbu11/PreSales/security/advisories/GHSA-q56c-76gq-653v). Redeploy with `sam build && sam deploy`; the table is retained and no seed step is needed.

### Fixed (advisory)
- `strip_trial` rejects adversary answers outside `1..len(lineup)`. `{"candidate": 0}` was resolved to the last lineup member and scored as a valid trial, which skews the lift that opens the calibration gate. Out-of-range answers are now stored as errored trials and ignored by `calibration`. Settled trials from v0.1.0 whose `guess_fixture_id` equals the last entry of `lineup_ids` deserve suspicion; re-running the 12 numbers-only trials puts the gate on clean evidence.
- Bedrock IAM is scoped to the stack region: `arn:aws:bedrock:${AWS::Region}::foundation-model/*` and same-region inference profiles, where v0.1.0 allowed any region.

### Hardened
- DynamoDB access is an explicit statement limited to `GetItem`, `PutItem`, `Query`, `UpdateItem` on the table ARN; the managed CRUD policy that also granted Delete and Scan is gone.
- The table carries `DeletionPolicy: Retain` and `UpdateReplacePolicy: Retain`; deleting the stack no longer destroys the calibration history.
- `ReservedConcurrentExecutions: 5` on the function bounds concurrent Bedrock fan-out.
- Request caps: `lineup_size` and synth `n` at most 50, `stripped` at most 200 KB, all rejected with a clear error before any model call instead of running into the 180 s timeout.
- `synth` generates in server-side batches of four; a single call for large `n` silently truncated at `max_tokens` and under-returned.
- `bump_rules` uses conditional writes and retries, so two bumps racing on the same base version both land (as base+1 and base+2) instead of the loser's rules and changelog entry vanishing.

### Added
- `tests/test_template.py`: static checks on `template.yaml` (Bedrock region scope, explicit DynamoDB actions, retained table, bounded concurrency).
- `SECURITY.md`, private vulnerability reporting enabled, repository description and topics.
- README names the users running strip-kit in their own accounts.

### Changed
- `lambda/__pycache__` is no longer tracked; `.gitignore` added.

## v0.1.0

First release: one Lambda, one DynamoDB table, Bedrock adversary; `strip` and `strip-lab` skills; seed with rules v2, prompt catalog, 12 fixtures and two inherited calibration rows.
