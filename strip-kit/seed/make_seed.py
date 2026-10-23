"""Builds seed_payload.json from rules.json, fixtures.json, prompts.json, inherited.json.
Run after editing any of them: python3 make_seed.py
"""
import json, pathlib
here = pathlib.Path(__file__).parent
payload = {
    "action": "seed",
    "rules": json.loads((here / "rules.json").read_text()),
    "fixtures": json.loads((here / "fixtures.json").read_text()),
    "prompts": json.loads((here / "prompts.json").read_text()),
    "inherited": json.loads((here / "inherited.json").read_text()),
}
(here / "seed_payload.json").write_text(json.dumps(payload, indent=1))
print("seed_payload.json:", len(payload["fixtures"]), "fixtures, rules v%s" % payload["rules"]["version"])
