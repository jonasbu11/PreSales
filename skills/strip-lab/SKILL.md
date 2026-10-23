---
name: strip-lab
description: Calibrate the de-identification rules the strip skill applies, by generating invented fixtures and running re-identification trials against an outside model on Bedrock. Produces one number per rules version and level, the lift over chance, and opens or closes the gate the strip skill checks. Trigger on "strip lab", "calibrate the strip", "run strip trials", "generate fixtures", "is the gate open", "bump the strip rules", or a scheduled calibration run. Never run on real client material.
---

# strip-lab

Two jobs, one loop. Fixtures are invented clients, scopes, and tickets that contain no real client, person, or engagement, so anything can be tested on them. The strip rules are what the strip skill applies before material leaves for an outside model. The rules are only trustworthy to the degree an adversary fails to undo them, and that is measured here, on fixtures, never on real material.

The number this skill produces is the re-identification rate of the current rules version at a level. Everything downstream depends on it: client-shaped material leaves only when the version is calibrated and under the acceptance bar.

## What this skill owns and never does

Owns: the fixture store, the rules (versioned), the trials, the calibration aggregate, and the decision to bump a version.

Delegates: applying the rules to real material to the strip skill; the adversary transport to the strip-kit function, which calls Bedrock.

Never:
- Sends real client material, real names, or real documents anywhere. A trial's lineup is synthetic end to end; if a real name would be needed to run a test, the test is not run.
- Edits a rules version in place. A change is a new version with a changelog line; old trials keep their version.
- Lets Claude grade its own strip. The adversary is the Bedrock head the function is configured with; Claude never picks the lineup answer.
- Uses an Anthropic model as the adversary. The function's `ADVERSARY_MODEL` should be the strongest non-Anthropic model the account can reach; a weak adversary under-reports leakage and a same-family adversary shares the stripper's blind spots.

## Step 0: Preconditions

Find the function exactly as the strip skill does (`config.json`, else the `app=strip-kit` tag). Then:

```
{"action": "ping"}
{"action": "get_rules"}
{"action": "calibration"}
{"action": "list_fixtures"}
```

No function: one line, stop. `ping` reports the adversary model; if it is an Anthropic model id, say so and stop until it is changed (template parameter `AdversaryModel`).

## Job A: Generate fixtures

Kinds and their prompts live in the function (`prompts`). Add a kind with `set_prompts`, never by editing this file.

```
{"action": "synth", "kind": "client", "n": 4}
```

Batches of four; the Lambda has a three-minute ceiling and eight on one call has run past it on slower models. Pass `model` to spread batches across models so the fixtures do not all share one model's habits. For scopes, pass the client list as context so scopes can reference clients by index:

```
{"action": "synth", "kind": "scope", "n": 4, "context": [{"index": 1, "name": "...", "industry": "..."}, ...]}
```

Read every batch once before keeping it. Retire (`{"action": "retire_fixture", "id": N}`) any fixture whose invented name collides with a real company Claude recognises, or that is a thin copy of another. A fixture the trials never touch is noise; `used_by` on each fixture shows which trials used it.

Kill signal for this job: no fixture's `used_by` grows for 30 days.

## Job B: Calibrate the rules

One trial is: pick a fixture, write a realistic document about it the way a real deliverable would read, strip that document under the current rules at the level under test exactly as the strip skill would, then fire the stripped text and a lineup at the adversary.

1. **Write the synthetic document.** A scope summary, an LOE rationale, a cost-estimate narrative, an email thread: whatever shape a consumer actually sends. Make it as specific as the real thing. A vague synthetic document flatters the rules.
2. **Strip it.** Apply `rules` in order at the level under test. Do the last rule (the adversarial read-back) honestly; this is the step the trials test.
3. **Fire.** The function builds the lineup from the fixture store, calls the adversary, and settles the trial in one call:

```
{"action": "strip_trial", "fixture_id": N, "stripped": "<text>", "rules_version": V, "level": "numbers-only", "lineup_size": 8, "lineup_model": "public"}
```

Lineup of eight by default. `lineup_model: public` is the calibration (what a searcher could find: name, industry, size, HQ, trait, stack). `full` is an upper bound on leakage, not the calibration. Vary the fixture and the document shape across trials; vary `model` if more than one strong non-Anthropic head is enabled.

4. **Read the rationale.** The reply's `rationale` names the clues the adversary used. That is the edit list for the next version. On numbers-only payloads, rationales are routinely confabulated (stacks, headcounts and cities that appear nowhere in the payload) and stated confidence is noise; weigh the hit, not the story.

Calibration state:

```
{"action": "calibration"}
{"action": "check_gate", "level": "<level>"}
```

A version is **calibrated** at `acceptance.min_trials` settled local trials and **usable** when `lift_over_chance <= acceptance.max_lift_over_chance`. Below `min_trials`, an inherited row for the same version and level stands in (status `inherited`); with no row at all, the version is uncalibrated and the strip skill treats it as failing. Rows tagged `inherited` came from another deployment's trials and should be replaced by local ones before anyone leans on them for a client deliverable: twelve local numbers-only trials is the first thing a new deployment should run.

## Step 3: Bump the version when the rationales demand it

When a version fails, write the next one from the rationales, not from theory: each clue the adversary named becomes a rule that removes that clue.

```
{"action": "bump_rules", "rules": [...full new list...], "note": "<trial results that forced it>", "cost": "<which question classes can no longer leave>"}
```

Rerun the same fixtures and document shapes first so the comparison is like for like, then widen.

**Kill signal for this job:** three consecutive versions each failing acceptance means client-shaped material at that level cannot be de-identified well enough to leave. Record it, set `acceptance.status` to `unachievable` on the next bump, and the strip skill falls back to a paid ZDR head or keeps the material home.

## Step 4: Report

Chat, short. Fixtures: how many, which kinds, which models, anything retired. Calibration: version, level, trials, hits, chance, lift, verdict against acceptance, and whether the row is local or inherited. For a failed version: the three most-cited clues from the rationales and the rule change each one forces. Never quote a fixture at length; they are test data, not content.

## Verification posture

- Requires a call every run: get_rules, calibration, every trial result.
- Never cached: a version's verdict. Re-read calibration; another user may have added trials.
- Assumed without a call: action signatures in the function's docstring.
