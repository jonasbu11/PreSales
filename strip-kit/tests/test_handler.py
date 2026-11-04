"""Runs the whole loop against the in-memory store with Bedrock stubbed.
python3 tests/test_handler.py
"""
import json, os, sys, pathlib
os.environ["STRIP_BACKEND"] = "memory"
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "lambda"))
import handler as h

calls = []
def fake_converse(system, user, model=None, max_tokens=4000, temperature=0.7):
    calls.append((system[:40], model))
    if "re-identification adversary" in system:
        # always guess candidate 1 so correctness is random against the shuffle
        return 'Sure! {"candidate": 1, "confidence": "high", "rationale": "industry and size"}'
    n = int(user.split("exactly ")[1].split()[0])
    return "```json\n" + json.dumps([{"name": f"Fake Co {i}", "industry": "X", "sub_industry": "Y",
        "size_employees": 10+i, "annual_revenue_usd": 1, "hq_city": "A", "hq_state": "B",
        "cloud_maturity": "none", "notable_trait": "t", "primary_contact_role": "r",
        "pain_points": ["a","b","c"], "current_stack": ["s"], "budget_band_usd": "1-2"} for i in range(n)]) + "\n```"
h.converse = fake_converse

def call(**ev):
    r = h.handler(ev)
    assert "error" not in r or ev.get("expect_error"), r
    return r

seed = json.load(open(pathlib.Path(__file__).parent.parent / "seed/seed_payload.json"))
assert h.handler({"action": "get_rules"})["error"]
r = call(**seed); assert r["fixtures"] == 12 and r["rules_version"] == 2 and r["inherited_rows"] == 2, r
assert "already seeded" in h.handler(seed)["error"]

rules = call(action="get_rules"); assert rules["version"] == 2 and len(rules["rules"]) == 12

# gate: inherited row carries numbers-only; narrative fails; unknown level uncalibrated
g = call(action="check_gate", level="numbers-only"); assert g["usable"] and g["status"] == "inherited", g
g = call(action="check_gate", level="narrative"); assert not g["usable"] and g["status"] == "failing", g
g = call(action="check_gate", level="nope"); assert g["status"] == "uncalibrated", g

# synth
s = call(action="synth", kind="client", n=4); assert len(s["ids"]) == 4 and s["ids"][0] == 13
assert h.handler({"action": "synth", "kind": "bogus"})["error"].startswith("unknown kind")
assert len(call(action="list_fixtures", kind="client")) == 16
call(action="retire_fixture", id=16); assert len(call(action="list_fixtures")) == 15
assert len(call(action="list_fixtures", include_retired=True)) == 16

# trials: 12 local numbers-only trials flip the gate from inherited to local
for i in range(12):
    t = call(action="strip_trial", fixture_id=1 + i % 12, stripped=f"design 40h build 120h test 30h fee 48000 phases 3 weeks 8 #{i}",
             rules_version=2, level="numbers-only")
    assert t["truth"] == 1 + i % 12 and t["confidence"] == "high"
cal = call(action="calibration")
local = [r for r in cal if r["source"] == "local"][0]
assert local["trials"] == 12 and local["chance_rate"] == 0.125 and abs(local["lift_over_chance"] - (local["hits"]/12 - 0.125)) < 1e-3, local
g = call(action="check_gate", level="numbers-only"); assert g["status"] in ("calibrated", "failing") and g["row"]["source"] == "local", g
assert len(call(action="list_trials", level="numbers-only")) == 12
assert any(f["used_by"] for f in call(action="list_fixtures"))

# lineup too small for a kind with few fixtures
e = h.handler({"action": "strip_trial", "fixture_id": 1, "stripped": "x", "rules_version": 2, "lineup_size": 40}); assert "only" in e["error"]

# request caps: rejected before any model call
before = len(calls)
e = h.handler({"action": "strip_trial", "fixture_id": 1, "stripped": "x", "rules_version": 2, "lineup_size": 51}); assert "lineup_size" in e["error"], e
e = h.handler({"action": "strip_trial", "fixture_id": 1, "stripped": "x", "rules_version": 2, "lineup_size": 1}); assert "lineup_size" in e["error"], e
e = h.handler({"action": "strip_trial", "fixture_id": 1, "stripped": "x" * (200 * 1024 + 1), "rules_version": 2, "level": "numbers-only"}); assert "limit is 204800" in e["error"], e
e = h.handler({"action": "strip_trial", "fixture_id": 1, "stripped": ["not", "text"], "rules_version": 2}); assert "string" in e["error"], e
e = h.handler({"action": "synth", "kind": "client", "n": 51}); assert "n must be" in e["error"], e
e = h.handler({"action": "synth", "kind": "client", "n": 0}); assert "n must be" in e["error"], e
assert len(calls) == before, "a capped request reached the model"

# synth batches server-side: 9 fixtures = 3 model calls (4, 4, 1), every one stored
before = len(calls)
s = call(action="synth", kind="client", n=9, context=[{"x": 1}])
assert len(s["ids"]) == 9 and len(calls) - before == 3, (len(s["ids"]), len(calls) - before)
assert len(call(action="list_fixtures", kind="client")) == 24

# bump requires a note, creates v3, keeps v2 readable
assert "note is required" in h.handler({"action": "bump_rules"})["error"]
b = call(action="bump_rules", rules=rules["rules"] + ["New rule."], note="12 trials, lift 0.3; adversary cited X", cost="questions about X cannot leave")
assert b["version"] == 3 and call(action="get_rules")["version"] == 3 and len(call(action="get_rules")["rules"]) == 13
assert call(action="get_rules_version", version=2)["version"] == 2
g = call(action="check_gate", level="numbers-only"); assert g["status"] == "uncalibrated" and g["rules_version"] == 3, g
g = call(action="check_gate", level="numbers-only", rules_version=2); assert g["row"]["source"] == "local"

# unachievable short-circuit
call(action="bump_rules", acceptance=dict(rules["acceptance"], status="unachievable"), note="three versions failed")
assert call(action="check_gate", level="numbers-only")["status"] == "unachievable"

# dispatch edge cases
assert "unknown action" in h.handler({"action": "zzz"})["error"]
assert h.handler({"body": json.dumps({"action": "ping"})})["ok"]
assert h.extract_json('text {"a":[1,2]} trailing') == {"a": [1, 2]}
print("all checks passed;", len(calls), "stubbed model calls")
