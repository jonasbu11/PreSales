# strip-kit

De-identification for anything that leaves for an outside model, packaged so each user can run it against their own AWS account.

Three pieces:

- `lambda/handler.py` and `template.yaml`: one Lambda, one DynamoDB table, Bedrock for the adversary and fixture generation. Deployed with SAM. Tagged `app=strip-kit` so the skills can find it.
- `../skills/strip`: the consumer. Loads the current rules from the function, applies them in session, checks the calibration gate, refuses when closed. Claude strips; the function never sees real material.
- `../skills/strip-lab`: the calibration loop. Generates invented fixtures, runs re-identification trials against the Bedrock adversary, aggregates the lift over chance, bumps rules versions from the adversary's rationales.

## Deploy (once per account)

Prerequisites: AWS CLI, SAM CLI, Bedrock model access enabled in the target region for the two models in `template.yaml` (`DefaultModel` for fixture generation, `AdversaryModel` for trials). Check what the account can reach:

    aws bedrock list-inference-profiles --region us-east-1 --query 'inferenceProfileSummaries[].inferenceProfileId'

Then:

    sam build
    sam deploy --guided --stack-name strip-kit --parameter-overrides AdversaryModel=<strongest non-Anthropic id>

The adversary must not be an Anthropic model: the stripper is Claude, and a same-family adversary shares its blind spots. Use the strongest non-Anthropic model the account can reach; a weak adversary under-reports leakage and the calibration built on it is worthless.

## Seed (once per table)

    aws lambda invoke --function-name strip-kit --cli-binary-format raw-in-base64-out --payload file://seed/seed_payload.json /dev/stdout

This loads rules v2, the prompt catalog, 12 invented client fixtures, and two inherited calibration rows. The inherited numbers-only row (12 trials, lift 0.042 against a 0.15 bar) opens the numbers-only gate immediately; it stands until the deployment has 12 local trials, after which local trials decide. The narrative row is failing and stays failing until someone proves otherwise. Seeding refuses to run twice.

To change the seed, edit `seed/rules.json`, `seed/fixtures.json`, `seed/prompts.json` or `seed/inherited.json` and run `python3 seed/make_seed.py`.

## Install the skills (per user)

The skills live in this repo at `skills/strip` and `skills/strip-lab`, next to the other presales skills; install them the same way. Each user needs the AWS connector pointed at an account where the function is deployed. On first use the skill discovers the function by tag and writes `config.json`; set `function_name` and `region` by hand to skip discovery.

## First run on a new deployment

1. `strip-lab`: ping, read calibration, confirm the adversary model is not Anthropic.
2. Run 12 numbers-only trials against the seeded fixtures so the gate stands on local evidence rather than the inherited row.
3. Generate 8 to 12 more client fixtures in batches of four so lineups are not always drawn from the same dozen.

## Function actions

See the docstring at the top of `lambda/handler.py`. Every call is `{"action": "<name>", ...}` and returns JSON. `strip-kit/tests/test_handler.py` runs the whole loop against an in-memory store with Bedrock stubbed:

    cd strip-kit && pip install boto3 pyyaml && python3 tests/test_handler.py && python3 tests/test_template.py

`tests/test_template.py` checks the SAM template's IAM scope and data-safety properties (region-scoped Bedrock access, explicit DynamoDB actions, retained table, bounded concurrency).

## What is deliberately not here

- No real client list. The threat model assumes the adversary holds it; the lineup is built from synthetic fixtures so the test never needs the real one.
- No real material. `strip_trial` takes a fixture id, not free text about a client.
- No in-place rule edits. `bump_rules` requires a changelog note.
