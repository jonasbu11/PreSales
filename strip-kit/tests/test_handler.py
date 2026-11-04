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

# adversary answers outside the lineup: rejected, never recorded as a settled trial
# ({"candidate": 0} used to resolve to lineup_ids[-1] via Python's negative index and
# count as a valid guess)
real_fake = h.converse
for bad in (0, -1, 9, 99):
    h.converse = lambda system, user, model=None, max_tokens=4000, temperature=0.7, bad=bad: (
        json.dumps({"candidate": bad, "confidence": "high", "rationale": "x"}) if "re-identification adversary" in system
        else real_fake(system, user, model, max_tokens, temperature))
    r = h.handler({"action": "strip_trial", "fixture_id": 1, "stripped": "fee 48000", "rules_version": 2, "level": "numbers-only"})
    assert "error" in r and "candidate" in r["error"], (bad, r)
    stored = [t for t in h.handler({"action": "list_trials", "limit": 1000}) if t["id"] == r["trial"]][0]
    assert stored["error"] and stored["settled_at"] is None and stored["correct"] is None, (bad, stored)
h.converse = real_fake
assert len([t for t in call(action="list_trials", level="numbers-only") if t["settled_at"]]) == 12, "out-of-range answers must not settle"
assert all(r["trials"] == 12 for r in call(action="calibration") if r["source"] == "local")

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

# concurrent bumps: a competing bump lands between this call's read and write; neither is lost
st = h.store()
real_get = st.get
state = {"fired": False}
def racing_get(pk, sk):
    r = real_get(pk, sk)
    if (pk, sk) == ("rules", "current") and not state["fired"]:
        state["fired"] = True
        st.get = real_get  # the inner bump reads normally
        inner = h.bump_rules({"note": "inner racer"})
        st.get = racing_get  # (outer still holds its stale read)
        assert inner["version"] == 4, inner
    return r
st.get = racing_get
outer = call(action="bump_rules", note="outer racer")
st.get = real_get
assert outer["version"] == 5, outer
assert call(action="get_rules_version", version=4)["changelog"][-1]["note"] == "inner racer"
assert call(action="get_rules")["version"] == 5 and call(action="get_rules")["changelog"][-1]["note"] == "outer racer"
assert [e["note"] for e in call(action="get_rules")["changelog"][-2:]] == ["inner racer", "outer racer"]

# unachievable short-circuit
call(action="bump_rules", acceptance=dict(rules["acceptance"], status="unachievable"), note="three versions failed")
assert call(action="check_gate", level="numbers-only")["status"] == "unachievable"

# dispatch edge cases
assert "unknown action" in h.handler({"action": "zzz"})["error"]
assert h.handler({"body": json.dumps({"action": "ping"})})["ok"]
assert h.extract_json('text {"a":[1,2]} trailing') == {"a": [1, 2]}

# ---------------------------------------------------------------- v0.1.2 cases
# Each case runs on a fresh seeded store so one failure cannot mask another.

def fresh():
    h._store = h.MemoryStore()
    assert h.handler(json.loads(json.dumps(seed)))["rules_version"] == 2
    return h.store()


h._sleep = lambda s: None  # bump_rules backs off between attempts; no wall-clock wait in tests


def case_pointer_move_lost_after_doc_landed():
    """put_if_absent wrote rules/3, then the pointer move failed with rules/current still at 2.
    v0.1.1 retried put_if_absent on rules/3, failed every attempt, and every later bump failed
    the same way: the store was wedged at version 2 for good."""
    st = fresh()
    real = st.put_if_version
    left = {"n": 1}

    def flaky(item, expected):
        if left["n"]:
            left["n"] -= 1
            assert st.get("rules", "00000003"), "doc should have landed before the pointer move"
            assert st.get("rules", "current")["version"] == 2
            raise h.ConditionFailed("injected: pointer move lost")
        return real(item, expected)

    st.put_if_version = flaky
    b = h.handler({"action": "bump_rules", "rules": ["after the lost pointer move"], "note": "lost pointer move"})
    st.put_if_version = real
    assert "error" not in b and b["version"] == 3, b
    r = h.handler({"action": "get_rules"})
    assert r["version"] == 3 and r["rules"] == ["after the lost pointer move"], r
    assert r["changelog"][-1]["note"] == "lost pointer move", r["changelog"][-1]
    b = h.handler({"action": "bump_rules", "note": "next bump"})
    assert b.get("version") == 4, b


def case_orphan_from_wedged_store():
    """A store wedged by v0.1.1: rules/3 exists with no pointer to it. A patched bump_rules
    replaces the orphan and lands as version 3 with its own content."""
    st = fresh()
    st.put({"pk": "rules", "sk": "00000003", "doc": {"version": 3, "rules": ["orphan"], "changelog": []}})
    b = h.handler({"action": "bump_rules", "rules": ["real"], "note": "over the orphan"})
    assert "error" not in b and b["version"] == 3, b
    r = h.handler({"action": "get_rules"})
    assert r["rules"] == ["real"] and r["changelog"][-1]["note"] == "over the orphan", r


def case_foreign_doc_is_never_adopted():
    """Regression guard (v0.1.1 passes this). A competing bump has written rules/3 but not yet
    moved rules/current. This bump must not adopt that doc and report success on it; it waits,
    sees the competitor's pointer move, and lands as 4 with its own content."""
    st = fresh()
    real_get = st.get
    phase = {"n": 0}

    def racing_get(pk, sk):
        if (pk, sk) == ("rules", "00000002") and phase["n"] == 0:
            phase["n"] = 1  # competitor's doc lands, its pointer move is still in flight
            inner = {"version": 3, "rules": ["inner"], "changelog": [{"version": 3, "note": "inner"}]}
            st.put({"pk": "rules", "sk": "00000003", "doc": inner, "bump_id": "competitor"})
        elif (pk, sk) == ("rules", "current") and phase["n"] == 1:
            phase["n"] = 2  # competitor's pointer move completes
            st.put({"pk": "rules", "sk": "current", "version": 3})
        return real_get(pk, sk)

    st.get = racing_get
    b = h.handler({"action": "bump_rules", "rules": ["outer"], "note": "outer"})
    st.get = real_get
    assert b.get("version") == 4, b
    assert h.handler({"action": "get_rules_version", "version": 3})["rules"] == ["inner"]
    r = h.handler({"action": "get_rules"})
    assert r["rules"] == ["outer"] and r["changelog"][-1]["note"] == "outer", r


def case_current_points_at_missing_version():
    st = fresh()
    st.put({"pk": "rules", "sk": "current", "version": 999})
    e = h.handler({"action": "get_rules"})
    assert e == {"error": "rules/current points at missing version 999"}, e
    e = h.handler({"action": "bump_rules", "note": "x"})
    assert e == {"error": "rules/current points at missing version 999"}, e


def case_concurrent_seeds():
    """Two seeds that both pass the rules/current guard: the second must refuse, not import."""
    st = fresh()
    n = len(h.handler({"action": "list_fixtures", "include_retired": True}))
    real_get = st.get
    st.get = lambda pk, sk: None if (pk, sk) == ("rules", "current") else real_get(pk, sk)
    e = h.handler(json.loads(json.dumps(seed)))
    st.get = real_get
    assert "already seeded" in e.get("error", ""), e
    assert len(h.handler({"action": "list_fixtures", "include_retired": True})) == n


failed = []
for name, fn in list(globals().items()):
    if name.startswith("case_") and callable(fn):
        try:
            fn()
            print("ok:", name)
        except Exception as ex:  # noqa: BLE001
            failed.append(name)
            print("FAIL:", name, "->", repr(ex)[:300])
if failed:
    sys.exit(f"{len(failed)} case(s) failed: {', '.join(failed)}")
print("all checks passed;", len(calls), "stubbed model calls")
