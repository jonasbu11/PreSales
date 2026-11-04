# Changelog

All notable changes to strip-kit and the strip skills. Versions are git tags; users deploying strip-kit should read the entry for every version between theirs and the one they are moving to.

## v0.1.3 (2026-11-04)

### Added
- `strip-kit/pyproject.toml`: the handler is installable as the `strip-kit` distribution (Python 3.12+, depends on `boto3`) and imports as `strip_kit.handler`. `lambda/` is mapped to the `strip_kit` package, so the SAM template is unchanged.
- `.github/workflows/publish-strip-kit.yml`: a `vX.Y.Z` tag runs the tests, builds, checks the metadata, verifies that the version matches the tag, and publishes to PyPI through Trusted Publishing.

Published to PyPI: `pip install strip-kit`. No behavior change to the Lambda.

## v0.1.2 (2026-11-03)

Security release. Advisory: [GHSA-5549-q5ww-6p64](https://github.com/jonasbu11/PreSales/security/advisories/GHSA-5549-q5ww-6p64). Redeploy with `sam build && sam deploy`; the table is retained and no seed step is needed.

### Fixed (advisory)
- `bump_rules` no longer wedges the store. In v0.1.1, if the version doc `rules/<n+1>` landed and the pointer move on `rules/current` then failed, every retry and every later bump failed on its own leftover doc and the rules could never be bumped again. Each version doc now carries the `bump_id` of the call that wrote it. A bump that finds its own doc at `n+1` retries only the pointer move. A bump that finds another call's doc there with `rules/current` still at `n` waits once, then replaces that exact orphan. A bump reports success only when the doc at its version is its own, so it never claims another caller's doc as its write.
- **Unwedging an existing store:** after upgrading, the next `bump_rules` call replaces the orphan `rules/<n+1>` and lands as `n+1`. Alternatively, delete the orphan item (`pk = rules`, `sk = <n+1 zero-padded to 8 digits>`) by hand before bumping. A store is wedged if `rules/<n+1>` exists while `rules/current` points at `n`.

### Fixed
- `seed` writes `rules/<v>` and `rules/current` conditionally; two concurrent seeds that both pass the `rules/current` guard can no longer both import (duplicate fixtures, overwritten rules). The second returns `rules already seeded`.
- `get_rules` and `bump_rules` return `{"error": "rules/current points at missing version <n>"}` when the pointer's doc is gone, instead of an opaque `TypeError`.
- `DynamoStore.put_if_version` aliases the `version` attribute through `ExpressionAttributeNames`.

### Added
- `tests/test_handler.py` runs the v0.1.2 cases on fresh stores, each reported independently: lost pointer move after the doc landed, orphan from a wedged store, competing in-flight bump never adopted, dangling `rules/current`, concurrent seeds.

### Changed
- Repository topic `sample` replaced with `aws-sam`.

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
