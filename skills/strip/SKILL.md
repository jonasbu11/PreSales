---
name: strip
description: De-identify client or engagement material before any of it leaves for an outside model (OpenAI, Gemini, a client-shared tool, any non-Bedrock head). Loads the current rules from the strip-kit function, applies them in session, checks the calibration gate for the chosen level, and refuses to send when the gate is closed. Trigger whenever a skill or the user is about to send client-shaped text to an external model: "send this to", "second opinion from", "ask GPT", "run this past", or any outside-head step inside another skill. Not for material going to Bedrock inside the firm's own account.
---

# strip

Claude strips. The function stores the rules and measures them; it never sees the material. That split is the whole design: the text being stripped is confidential by definition, so nothing can delegate the strip to another model, and the only honest check on it is the adversary trial run on synthetic fixtures (strip-lab).

## Step 0: Find the function

Read `config.json` next to this file. If it has `function_name` and `region`, use them. If not, discover once and write them back:

```
aws resourcegroupstaggingapi get-resources --tag-filters Key=app,Values=strip-kit --resource-type-filters lambda:function --region <region> --query 'ResourceTagMappingList[].ResourceARN' --output text
```

No match in the default region: try the regions in `config.json.search_regions`. No match anywhere: one line, "strip-kit is not deployed in this AWS account; see README", and the material stays home. Never fall back to the bundled `rules.json` for a real send: that file exists so the rules can be read offline, and a send without a live gate check is a send without a calibration.

Every call is one AWS CLI invocation through the AWS connector:

```
aws lambda invoke --function-name <function_name> --region <region> --cli-binary-format raw-in-base64-out --payload '<json>' /dev/stdout
```

## Step 1: Rules and level

```
{"action": "get_rules"}
```

Pick the level from what the consumer is asking:

- **numbers-only**: the question is arithmetic, loading, rate, or phase logic. Task rows as generic labels (design, build, integrate, test, document) with hours, load percentages, rate, fee, phase count and weeks, funding as "partner-funded" or "not funded". No nouns from the engagement at all.
- **narrative**: the question needs prose about the engagement. Every rule applies. This level has failed every calibration so far; expect the gate to be closed and plan for it.

## Step 2: Gate

```
{"action": "check_gate", "level": "<level>"}
```

`usable: true` with status `calibrated` or `inherited`: proceed. Anything else: do not send. Status `inherited` means the deployment is standing on a calibration imported from another deployment until it has twelve local trials; it counts, but say so in the report if the send is for a client deliverable.

Closed gate, in order of preference: drop to numbers-only if the question survives it; send to a paid zero-data-retention head if the calling skill names one; keep the material home and answer with Claude alone. Say which in one line.

## Step 3: Strip

Apply `rules` from the get_rules reply in order, on the actual text, in session. Do the last rule honestly: read the result once as an adversary holding the firm's client list, and if any two remaining details together would pick the client out, remove one of them. The trials in strip-lab measure whether this step is being done honestly; a lazy read-back here shows up as a failing version there.

Keep a private two-line record for the session: level, rules version, and which classes of detail were removed (not the details). The consumer skill may want it for its own log.

## Step 4: Send

Hand the stripped text to the calling skill's transport. Nothing in this skill sends anything.

## What never leaves at any level

Real names, identifiers, quoted client text, the author's own prose in house style, secrets, internal system ids, and anything the gate has not been opened for. If a real name would be needed to make the question answerable, the question does not leave.

## Verification posture

- Requires a call every run: get_rules, check_gate. Never cached across sessions; another user's trials may have closed the gate.
- Assumed without a call: the CLI syntax above, which is stable.
- `rules.json` in this folder is a convenience copy regenerated from get_rules on release. The function is canonical.
