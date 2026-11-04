"""strip-kit: one Lambda, one DynamoDB table, Bedrock for the outside head.

Event shape: {"action": "<name>", ...args}. Every action returns JSON.

Actions
  get_rules                              current rules document
  get_rules_version   {version}          a specific version
  bump_rules          {rules, levels?, note, cost?}  new version from a changelog note
  check_gate          {level, rules_version?, lineup_model?}  usable / uncalibrated / failing
  calibration         {}                 aggregate per (rules_version, level, lineup_model)
  synth               {kind, n?, model?, context?}  generate n fixtures of a kind via Bedrock
  list_fixtures       {kind?, include_retired?}
  retire_fixture      {id}
  strip_trial         {fixture_id, stripped, rules_version, level, lineup_size?, model?, lineup_model?}
  list_trials         {rules_version?, level?, limit?}
  seed                {rules, fixtures, prompts, inherited?}  one-time import; refuses if rules exist
  prompts             {}                 the synth prompt catalog
  set_prompts         {prompts}          replace the catalog
  ping                {}

The strip itself is never performed here. The consumer (Claude in session) strips
under the rules; this function only stores rules, fixtures, trials, and runs the
adversary head. Real client material never reaches this function: strip_trial
takes synthetic fixtures only, and the lineup is built from the fixture store.
"""

import json
import os
import random
import re
import time
import hashlib
from decimal import Decimal

TABLE = os.environ.get("STRIP_TABLE", "")
REGION = os.environ.get("AWS_REGION", "us-east-1")
DEFAULT_MODEL = os.environ.get("DEFAULT_MODEL", "us.amazon.nova-pro-v1:0")
ADVERSARY_MODEL = os.environ.get("ADVERSARY_MODEL", DEFAULT_MODEL)
BACKEND = os.environ.get("STRIP_BACKEND", "dynamo")  # "memory" for tests

# Request caps. Everything above these is rejected up front rather than burning the
# 180s timeout on an oversized lineup, fixture batch or document.
MAX_LINEUP = 50
MAX_SYNTH_N = 50
MAX_STRIPPED_BYTES = 200 * 1024


# ---------------------------------------------------------------- storage

class MemoryStore:
    """Same interface as DynamoStore; used by tests."""

    def __init__(self):
        self.items = {}

    def get(self, pk, sk):
        return self.items.get((pk, sk))

    def put(self, item):
        self.items[(item["pk"], item["sk"])] = item

    def query(self, pk):
        return sorted(
            (v for (p, _), v in self.items.items() if p == pk),
            key=lambda x: x["sk"],
        )

    def next_id(self, name):
        c = self.items.get(("counter", name), {"pk": "counter", "sk": name, "n": 0})
        c["n"] += 1
        self.items[("counter", name)] = c
        return c["n"]


class DynamoStore:
    def __init__(self, table):
        import boto3
        self.t = boto3.resource("dynamodb", region_name=REGION).Table(table)

    def get(self, pk, sk):
        r = self.t.get_item(Key={"pk": pk, "sk": sk})
        return _undecimal(r.get("Item"))

    def put(self, item):
        self.t.put_item(Item=json.loads(json.dumps(item), parse_float=Decimal))

    def query(self, pk):
        from boto3.dynamodb.conditions import Key
        out, kw = [], {"KeyConditionExpression": Key("pk").eq(pk)}
        while True:
            r = self.t.query(**kw)
            out.extend(r.get("Items", []))
            if "LastEvaluatedKey" not in r:
                break
            kw["ExclusiveStartKey"] = r["LastEvaluatedKey"]
        return _undecimal(out)

    def next_id(self, name):
        r = self.t.update_item(
            Key={"pk": "counter", "sk": name},
            UpdateExpression="ADD n :one",
            ExpressionAttributeValues={":one": 1},
            ReturnValues="UPDATED_NEW",
        )
        return int(r["Attributes"]["n"])


def _undecimal(o):
    if isinstance(o, list):
        return [_undecimal(x) for x in o]
    if isinstance(o, dict):
        return {k: _undecimal(v) for k, v in o.items()}
    if isinstance(o, Decimal):
        return int(o) if o == o.to_integral_value() else float(o)
    return o


_store = None


def store():
    global _store
    if _store is None:
        _store = MemoryStore() if BACKEND == "memory" else DynamoStore(TABLE)
    return _store


def _sk(n):
    return f"{int(n):08d}"


# ---------------------------------------------------------------- bedrock

def _bedrock():
    import boto3
    return boto3.client("bedrock-runtime", region_name=REGION)


def converse(system, user, model=None, max_tokens=4000, temperature=0.7):
    """One call to the Bedrock Converse API. Returns the text reply."""
    r = _bedrock().converse(
        modelId=model or DEFAULT_MODEL,
        system=[{"text": system}],
        messages=[{"role": "user", "content": [{"text": user}]}],
        inferenceConfig={"maxTokens": max_tokens, "temperature": temperature},
    )
    return "".join(c.get("text", "") for c in r["output"]["message"]["content"])


# ---------------------------------------------------------------- json helpers

def extract_json(txt):
    """Pull the first JSON object or array out of a model reply."""
    txt = txt.strip()
    txt = re.sub(r"^```(?:json)?\s*|\s*```$", "", txt)
    starts = [i for i in (txt.find("{"), txt.find("[")) if i >= 0]
    if not starts:
        raise ValueError("no JSON in reply")
    s = min(starts)
    closer = "}" if txt[s] == "{" else "]"
    e = txt.rfind(closer)
    return json.loads(txt[s:e + 1])


def sha1(s):
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- rules

def get_rules(args=None):
    cur = store().get("rules", "current")
    if not cur:
        return {"error": "no rules seeded"}
    return store().get("rules", _sk(cur["version"]))["doc"]


def get_rules_version(args):
    item = store().get("rules", _sk(args["version"]))
    return item["doc"] if item else {"error": f"no rules version {args['version']}"}


def bump_rules(args):
    """New version. Never edits in place. `note` is required and goes to the changelog."""
    if not args.get("note"):
        return {"error": "note is required: state the trial results that forced the change and what the new rules cost"}
    doc = get_rules()
    if "error" in doc:
        return doc
    new = json.loads(json.dumps(doc))
    new["version"] = doc["version"] + 1
    if "rules" in args:
        new["rules"] = args["rules"]
    if "levels" in args:
        new["levels"] = args["levels"]
    if "acceptance" in args:
        new["acceptance"] = args["acceptance"]
    entry = {"version": new["version"], "date": time.strftime("%Y-%m-%d"), "note": args["note"]}
    if args.get("cost"):
        entry["cost"] = args["cost"]
    new.setdefault("changelog", []).append(entry)
    store().put({"pk": "rules", "sk": _sk(new["version"]), "doc": new})
    store().put({"pk": "rules", "sk": "current", "version": new["version"]})
    return {"version": new["version"], "changelog_entry": entry}


# ---------------------------------------------------------------- fixtures

def list_fixtures(args=None):
    args = args or {}
    items = store().query("fixture")
    out = []
    for it in items:
        if it.get("retired_at") and not args.get("include_retired"):
            continue
        if args.get("kind") and it["kind"] != args["kind"]:
            continue
        out.append({"id": it["id"], "kind": it["kind"], "payload": it["payload"],
                    "retired_at": it.get("retired_at"), "used_by": it.get("used_by", []),
                    "source": it.get("source")})
    return out


def _put_fixture(kind, payload, source):
    fid = store().next_id("fixture")
    item = {"pk": "fixture", "sk": _sk(fid), "id": fid, "kind": kind, "payload": payload,
            "source": source, "created_at": _now(), "used_by": []}
    store().put(item)
    return fid


def retire_fixture(args):
    item = store().get("fixture", _sk(args["id"]))
    if not item:
        return {"error": f"no fixture {args['id']}"}
    item["retired_at"] = _now()
    store().put(item)
    return {"id": item["id"], "retired_at": item["retired_at"]}


def prompts(args=None):
    p = store().get("prompts", "catalog")
    return p["doc"] if p else {"error": "no prompt catalog seeded"}


def set_prompts(args):
    store().put({"pk": "prompts", "sk": "catalog", "doc": args["prompts"]})
    return {"ok": True, "kinds": sorted(args["prompts"].get("kinds", {}).keys())}


def synth(args):
    """Generate n fixtures of a kind. Batches of four; larger batches time out on light heads."""
    kind = args["kind"]
    n = int(args.get("n", 4))
    if not 1 <= n <= MAX_SYNTH_N:
        return {"error": f"n must be between 1 and {MAX_SYNTH_N}, got {n}"}
    cat = prompts()
    if "error" in cat:
        return cat
    spec = cat["kinds"].get(kind)
    if not spec:
        return {"error": f"unknown kind {kind}; add it with set_prompts"}
    user = f"Generate exactly {n} objects. Schema: {spec['schema']}"
    if args.get("context") is not None:
        user += "\n\nContext (reference by index where the schema allows):\n" + json.dumps(args["context"])
    model = args.get("model") or DEFAULT_MODEL
    txt = converse(spec["system"], user, model=model, temperature=0.9)
    try:
        objs = extract_json(txt)
    except Exception as e:  # noqa: BLE001
        return {"error": f"unparseable head reply: {e}", "head": txt[:2000]}
    if isinstance(objs, dict):
        objs = [objs]
    ids = [_put_fixture(kind, o, model) for o in objs]
    return {"kind": kind, "model": model, "ids": ids,
            "fixtures": [{"id": i, "payload": o} for i, o in zip(ids, objs)]}


# ---------------------------------------------------------------- trials

ADVERSARY_SYSTEM = (
    "You are a re-identification adversary with web search access. You will see a de-identified "
    "consulting document and a numbered lineup of candidate organisations with their public profiles, "
    "exactly one of which is the true source. Pick the candidate the document was written about. Use "
    "every clue: industry, size, region, stack, engagement shape, phrasing. Reply with ONLY a JSON "
    'object: {"candidate": <number>, "confidence": "high|medium|low", "rationale": "<one sentence '
    'naming the clues you used>"}.'
)


def _public_profile(kind, payload):
    if kind != "client":
        return payload
    return {
        "name": payload.get("name"), "industry": payload.get("industry"),
        "sub_industry": payload.get("sub_industry"), "size_employees": payload.get("size_employees"),
        "hq": ", ".join(x for x in (payload.get("hq_city"), payload.get("hq_state")) if x),
        "notable_trait": payload.get("notable_trait"), "current_stack": payload.get("current_stack"),
    }


def strip_trial(args):
    """Fire one lineup at the adversary head and settle the trial synchronously."""
    fid = int(args["fixture_id"])
    target = store().get("fixture", _sk(fid))
    if not target:
        return {"error": f"no fixture {fid}"}
    kind = target["kind"]
    level = args.get("level", "narrative")
    size = int(args.get("lineup_size", 8))
    if not 2 <= size <= MAX_LINEUP:
        return {"error": f"lineup_size must be between 2 and {MAX_LINEUP}, got {size}"}
    lineup_model = args.get("lineup_model", "public")
    rules_version = int(args["rules_version"])
    stripped = args["stripped"]
    if not isinstance(stripped, str):
        return {"error": "stripped must be a string"}
    nbytes = len(stripped.encode("utf-8"))
    if nbytes > MAX_STRIPPED_BYTES:
        return {"error": f"stripped is {nbytes} bytes; the limit is {MAX_STRIPPED_BYTES}"}
    model = args.get("model") or ADVERSARY_MODEL

    pool = [f for f in store().query("fixture")
            if f["kind"] == kind and f["id"] != fid and not f.get("retired_at")]
    if len(pool) < size - 1:
        return {"error": f"only {len(pool)} other active fixtures of kind {kind}; need {size - 1}"}
    lineup = random.sample(pool, size - 1) + [target]
    random.shuffle(lineup)
    lineup_ids = [f["id"] for f in lineup]
    lineup_json = [
        {"candidate": i + 1,
         "profile": _public_profile(kind, f["payload"]) if lineup_model == "public" else f["payload"]}
        for i, f in enumerate(lineup)
    ]

    tid = store().next_id("trial")
    trial = {"pk": "trial", "sk": _sk(tid), "id": tid, "rules_version": rules_version,
             "strip_level": level, "lineup_model": lineup_model, "fixture_id": fid,
             "lineup_ids": lineup_ids, "stripped_sha1": sha1(stripped), "head": model,
             "created_at": _now()}
    try:
        txt = converse(ADVERSARY_SYSTEM,
                       "DOCUMENT:\n" + stripped + "\n\nLINEUP:\n" + json.dumps(lineup_json),
                       model=model, temperature=0.2)
    except Exception as e:  # noqa: BLE001
        trial["error"] = str(e)
        store().put(trial)
        return {"trial": tid, "error": f"head call failed: {e}"}
    try:
        j = extract_json(txt)
        guess_ord = int(j["candidate"])
        guess_id = lineup_ids[guess_ord - 1]
    except Exception as e:  # noqa: BLE001
        trial["error"] = "unparseable adversary reply"
        trial["raw"] = txt[:2000]
        store().put(trial)
        return {"trial": tid, "error": f"unparseable adversary reply: {e}", "head": txt[:500]}

    trial.update({"guess_fixture_id": guess_id, "correct": guess_id == fid,
                  "confidence": j.get("confidence"), "rationale": j.get("rationale"),
                  "settled_at": _now()})
    store().put(trial)
    for f in lineup:
        f.setdefault("used_by", []).append({"strip_trial": tid, "at": trial["settled_at"]})
        store().put(f)
    return {"trial": tid, "correct": trial["correct"], "guess": guess_id, "truth": fid,
            "confidence": trial["confidence"], "rationale": trial["rationale"], "head": model}


def list_trials(args=None):
    args = args or {}
    out = []
    for t in store().query("trial"):
        if args.get("rules_version") and t["rules_version"] != int(args["rules_version"]):
            continue
        if args.get("level") and t["strip_level"] != args["level"]:
            continue
        out.append({k: t.get(k) for k in ("id", "rules_version", "strip_level", "lineup_model",
                                           "fixture_id", "guess_fixture_id", "correct", "confidence",
                                           "rationale", "head", "settled_at", "error")})
    lim = int(args.get("limit", 50))
    return out[-lim:]


# ---------------------------------------------------------------- calibration

def calibration(args=None):
    """Aggregate settled trials per (rules_version, strip_level, lineup_model).

    Mirrors v_strip_calibration: hit_rate, chance_rate = 1/avg_lineup, lift = hit_rate - chance.
    Inherited rows (seeded from a previous deployment) are returned alongside with source=inherited.
    """
    groups = {}
    for t in store().query("trial"):
        if not t.get("settled_at"):
            continue
        k = (t["rules_version"], t["strip_level"], t["lineup_model"])
        g = groups.setdefault(k, {"trials": 0, "hits": 0, "lineup_sum": 0, "last_trial": None})
        g["trials"] += 1
        g["hits"] += 1 if t["correct"] else 0
        g["lineup_sum"] += len(t["lineup_ids"])
        g["last_trial"] = max(g["last_trial"] or "", t["settled_at"])
    rows = []
    for (v, lvl, lm), g in sorted(groups.items()):
        avg = g["lineup_sum"] / g["trials"]
        hr = g["hits"] / g["trials"]
        rows.append({"rules_version": v, "strip_level": lvl, "lineup_model": lm, "trials": g["trials"],
                     "hits": g["hits"], "hit_rate": round(hr, 3), "avg_lineup": avg,
                     "chance_rate": round(1 / avg, 3), "lift_over_chance": round(hr - 1 / avg, 3),
                     "last_trial": g["last_trial"], "source": "local"})
    for it in store().query("inherited"):
        rows.append(dict(it["row"], source="inherited"))
    return rows


def check_gate(args):
    """Is the current (or given) rules version usable for client-shaped material at this level?

    Local trials decide once they reach acceptance.min_trials. Below that, an inherited row for the
    same version/level/lineup_model stands in, flagged status=inherited. No row at all: uncalibrated.
    """
    level = args["level"]
    lineup_model = args.get("lineup_model", "public")
    doc = get_rules()
    if "error" in doc:
        return doc
    version = int(args.get("rules_version") or doc["version"])
    acc = doc.get("acceptance", {})
    min_trials = int(acc.get("min_trials", 12))
    max_lift = float(acc.get("max_lift_over_chance", 0.15))
    if acc.get("status") == "unachievable":
        return {"usable": False, "status": "unachievable", "rules_version": version, "level": level,
                "reason": "acceptance.status is unachievable; send to a paid ZDR head or keep it home"}
    rows = [r for r in calibration()
            if r["rules_version"] == version and r["strip_level"] == level and r["lineup_model"] == lineup_model]
    local = next((r for r in rows if r["source"] == "local"), None)
    inherited = next((r for r in rows if r["source"] == "inherited"), None)
    base = {"rules_version": version, "level": level, "lineup_model": lineup_model,
            "acceptance": {"min_trials": min_trials, "max_lift_over_chance": max_lift}}
    if local and local["trials"] >= min_trials:
        ok = local["lift_over_chance"] <= max_lift
        return dict(base, usable=ok, status="calibrated" if ok else "failing", row=local)
    if inherited:
        ok = inherited["lift_over_chance"] <= max_lift and inherited["trials"] >= min_trials
        return dict(base, usable=ok, status="inherited" if ok else "failing",
                    local_trials=local["trials"] if local else 0, row=inherited,
                    note="standing on an inherited calibration until local trials reach min_trials")
    return dict(base, usable=False, status="uncalibrated",
                local_trials=local["trials"] if local else 0,
                reason=f"fewer than {min_trials} settled local trials and no inherited row")


# ---------------------------------------------------------------- seed

def seed(args):
    """One-time import. Refuses if rules already exist so a re-run cannot clobber a live store."""
    if store().get("rules", "current"):
        return {"error": "rules already seeded; use bump_rules / synth instead"}
    doc = args["rules"]
    store().put({"pk": "rules", "sk": _sk(doc["version"]), "doc": doc})
    store().put({"pk": "rules", "sk": "current", "version": doc["version"]})
    if args.get("prompts"):
        set_prompts({"prompts": args["prompts"]})
    ids = [_put_fixture(f["kind"], f["payload"], f.get("source", "seed")) for f in args.get("fixtures", [])]
    n_inh = 0
    for row in args.get("inherited", []):
        n_inh += 1
        store().put({"pk": "inherited", "sk": _sk(n_inh), "row": row})
    return {"rules_version": doc["version"], "fixtures": len(ids), "inherited_rows": n_inh,
            "prompt_kinds": sorted((args.get("prompts") or {}).get("kinds", {}).keys())}


# ---------------------------------------------------------------- dispatch

def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


ACTIONS = {
    "ping": lambda a: {"ok": True, "table": TABLE, "region": REGION, "default_model": DEFAULT_MODEL,
                       "adversary_model": ADVERSARY_MODEL},
    "get_rules": get_rules, "get_rules_version": get_rules_version, "bump_rules": bump_rules,
    "check_gate": check_gate, "calibration": calibration,
    "synth": synth, "list_fixtures": list_fixtures, "retire_fixture": retire_fixture,
    "prompts": prompts, "set_prompts": set_prompts,
    "strip_trial": strip_trial, "list_trials": list_trials,
    "seed": seed,
}


def handler(event, context=None):
    if isinstance(event, str):
        event = json.loads(event)
    if "body" in event and isinstance(event["body"], str):  # API Gateway proxy shape, if ever fronted
        event = json.loads(event["body"])
    action = event.get("action")
    fn = ACTIONS.get(action)
    if not fn:
        return {"error": f"unknown action {action}", "actions": sorted(ACTIONS)}
    try:
        return fn(event)
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}", "action": action}
