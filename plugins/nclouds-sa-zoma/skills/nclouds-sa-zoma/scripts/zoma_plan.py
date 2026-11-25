#!/usr/bin/env python3
"""zoma_plan.py: map a SOW context.json and an LOE workbook to a Zoma push plan,
and gate a Zoma read-back against that plan.

    zoma_plan.py plan  --context context.json --loe LOE.xlsx --out plan.json [--config c.json] [--set key=value ...]
    zoma_plan.py check --plan plan.json --readback readback.json
    zoma_plan.py selftest

plan writes nothing to Zoma. check exits 1 when any gate item is FAIL.
"""
import argparse
import json
import math
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG = os.path.join(HERE, "..", "config.json")

SECTION_NAMES = {
    "1.1": "Project Overview", "1.2": "AWS Partnership", "2.1": "Pre-Requirements",
    "2.2": "Project Assumptions", "2.3": "Scope", "2.4": "Success Criteria",
    "2.5": "Exclusions", "2.6": "Timeline and Customer Involvement",
    "3.1": "Customer Responsibilities", "3.2": "nClouds Responsibilities",
    "3.3": "Shared Responsibilities", "3.4": "Change Control", "4.0": "Billing",
    "4.1": "Invoice Summary", "4.2": "Invoicing Schedule",
}
REF = re.compile(r"\bSection\s+(\d\.\d)(?:\.(\d+))?")


def load_config(path=None, sets=None):
    cfg = json.load(open(path or DEFAULT_CONFIG))
    for s in sets or []:
        k, sep, v = s.partition("=")
        if not sep or k not in cfg:
            sys.exit(f"unknown config key: {k}")
        try:
            cfg[k] = json.loads(v)
        except ValueError:
            cfg[k] = v
    return cfg


def norm(s):
    s = "" if s is None else str(s)
    for a, b in (("’", "'"), ("‘", "'"), ("“", '"'), ("”", '"'), (" ", " ")):
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", s).strip()


def money(s):
    if s is None:
        return None
    t = str(s).strip()
    m = re.search(r"[\d,]+(?:\.\d+)?", t)
    if not m:
        return None
    v = float(m.group(0).replace(",", ""))
    return -v if t.startswith(("(", "-")) else v


def fnum(v):
    try:
        return float(str(v).replace(",", "").replace("$", "").replace("%", ""))
    except (TypeError, ValueError):
        return None


def close(a, b, tol):
    return a is not None and b is not None and abs(a - b) <= tol


def yes(v):
    return norm(v).lower() in ("yes", "true", "y")


def pct_label(rate):
    return f"{rate * 100:g}%"


def flatten(slot):
    """A base-template slot (string, list, heading group, intro/items/outro) as a flat list of lines."""
    if slot is None:
        return []
    if isinstance(slot, str):
        return [p for p in (norm(x) for x in re.split(r"\n\s*\n", slot)) if p]
    if isinstance(slot, list):
        out = []
        for it in slot:
            out += flatten(it)
        return out
    if isinstance(slot, dict):
        if any(k in slot for k in ("items", "intro", "outro")):
            return flatten(slot.get("intro")) + flatten(slot.get("items")) + flatten(slot.get("outro"))
        h, t, b = norm(slot.get("heading")), norm(slot.get("text")), flatten(slot.get("bullets"))
        lines = ([t] if t else []) + b
        if not lines:
            return [h] if h else []
        return [f"{h}: {x}" if h else x for x in lines]
    return [norm(slot)]


def scope_headings(scope):
    items = scope.get("items") if isinstance(scope, dict) else scope
    return [norm(i.get("heading")) for i in (items or []) if isinstance(i, dict) and i.get("heading")]


def rewrite_refs(text, heads, unresolved):
    def sub(m):
        base, n = m.group(1), m.group(2)
        if base == "2.3" and n and 0 < int(n) <= len(heads):
            return f'the "{heads[int(n) - 1]}" scope item'
        if base in SECTION_NAMES:
            return f"the {SECTION_NAMES[base]} section"
        unresolved.append(m.group(0))
        return m.group(0)
    return REF.sub(sub, text)


def read_loe(path, cfg):
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=False)
    ws = wb["LOE"] if "LOE" in wb.sheetnames else wb.active
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    hi = next((i for i, r in enumerate(rows) if r and norm(r[0]).lower() == "task"), None)
    if hi is None:
        sys.exit("LOE: no header row starting with Task")
    head = [norm(c).lower() for c in rows[hi]]
    if "basis" not in head:
        sys.exit("LOE: no Basis column")
    bi = head.index("basis")
    mid = head[1:bi]
    if "total" in mid:
        hour_cols = [1 + mid.index("total")]
    elif "hours" in mid:
        hour_cols = [1 + mid.index("hours")]
    else:
        hour_cols = list(range(1, bi))
    sections, cur, loading, load = [], None, False, {}
    for r in rows[hi + 1:]:
        r = r + [None] * (bi + 1 - len(r))
        task = norm(r[0])
        if not task:
            continue
        vals = [r[i] for i in hour_cols]
        basis = norm(r[bi])
        nums = [float(v) for v in vals if isinstance(v, (int, float)) and not isinstance(v, bool)]
        formula = any(isinstance(v, str) and v.startswith("=") for v in vals)
        low = task.lower()
        if not nums and not formula and not basis:
            loading = low == cfg["loading_section"].lower()
            if not loading:
                cur = {"name": task, "rows": []}
                sections.append(cur)
            continue
        if loading or low.startswith("total loaded") or re.search(r"%\s+of engineering", low):
            m = re.search(r"(\d+(?:\.\d+)?)\s*%", task)
            key = "pm" if low.startswith("project management") else "risk" if low.startswith("risk") else "total"
            load[key] = {"rate": float(m.group(1)) / 100 if m else None, "basis": basis,
                         "hours": sum(nums) if nums else None}
            continue
        if not nums:
            sys.exit(f"LOE: task row has no numeric hours: {task}")
        if cur is None:
            cur = {"name": cfg["default_section"], "rows": []}
            sections.append(cur)
        cur["rows"].append({"task": task, "hours": round(sum(nums), 2), "basis": basis})
    if not any(s["rows"] for s in sections):
        sys.exit("LOE: no task rows found")
    return [s for s in sections if s["rows"]], load


def build_plan(ctx, loe_path, cfg):
    warns = []
    sections, load = read_loe(loe_path, cfg)
    eng = round(sum(r["hours"] for s in sections for r in s["rows"]), 2)

    def rate(key):
        v = cfg[f"{key}_rate"]
        if v == "loe":
            got = (load.get(key) or {}).get("rate")
            if got is not None:
                return got, "loe"
            warns.append(f"LOE states no {key} rate; used fallback {pct_label(cfg[key + '_rate_fallback'])}")
            return float(cfg[f"{key}_rate_fallback"]), "fallback"
        got = (load.get(key) or {}).get("rate")
        if got is not None and abs(got - float(v)) > 1e-9:
            warns.append(f"config {key}_rate {pct_label(float(v))} overrides the LOE's {pct_label(got)}")
        return float(v), "config"

    pm_rate, pm_src = rate("pm")
    risk_rate, risk_src = rate("risk")
    pm, risk = round(eng * pm_rate, 1), round(eng * risk_rate, 1)
    if cfg["hour_rounding"] == "whole":
        pm, risk = float(math.ceil(pm)), float(math.ceil(risk))
    elif cfg["hour_rounding"] != "none":
        sys.exit("hour_rounding must be none or whole")
    total = round(eng + pm + risk, 2)
    loe_total = (load.get("total") or {}).get("hours")
    if loe_total is not None and abs(loe_total - total) > 0.11:
        warns.append(f"LOE total loaded hours {loe_total:g} differs from the plan's {total:g}")

    heads = scope_headings(ctx.get("scope"))
    unresolved = []
    if cfg["section_refs"] == "names":
        fix = lambda t: rewrite_refs(t, heads, unresolved)
    elif cfg["section_refs"] == "keep":
        fix = lambda t: t
    else:
        sys.exit("section_refs must be names or keep")

    hide = [re.compile(p, re.I) for p in cfg["hide_from_sow_patterns"]]
    ecol = cfg["engineering_column"]
    rows = []
    for s in sections:
        for r in s["rows"]:
            rows.append({"section": s["name"], "task": fix(r["task"]), "hours": r["hours"], "basis": r["basis"],
                         "column": ecol, "show": not any(h.search(r["task"]) for h in hide), "kind": "task"})
    if cfg["pm_placement"] not in ("row", "role_column"):
        sys.exit("pm_placement must be row or role_column")
    ls = cfg["loading_section"]
    rows.append({"section": ls, "task": f"Project management ({pct_label(pm_rate)} of engineering effort)",
                 "hours": pm, "basis": (load.get("pm") or {}).get("basis") or f"{pct_label(pm_rate)} of {eng:g} engineering hours",
                 "column": ecol if cfg["pm_placement"] == "row" else cfg["pm_column"], "show": False, "kind": "pm"})
    rows.append({"section": ls, "task": f"Risk ({pct_label(risk_rate)} of engineering effort)",
                 "hours": risk, "basis": (load.get("risk") or {}).get("basis") or f"{pct_label(risk_rate)} of {eng:g} engineering hours",
                 "column": ecol, "show": False, "kind": "risk"})
    seen = {}
    for r in rows:
        seen[norm(r["task"])] = seen.get(norm(r["task"]), 0) + 1
    twice = [k for k, n in seen.items() if n > 1]
    if twice:
        sys.exit("LOE: duplicate task names cannot be gated: " + "; ".join(twice))
    column_totals = {}
    for r in rows:
        column_totals[r["column"]] = round(column_totals.get(r["column"], 0) + r["hours"], 2)

    assumptions = [fix(x) for x in flatten(ctx.get("assumptions"))]
    assumptions += [fix(cfg["prerequisite_prefix"] + x) for x in flatten(ctx.get("prerequisites"))]
    exclusions = [fix(x) for x in flatten(ctx.get("exclusions"))]

    lines = [(norm(b.get("name")), money(b.get("price"))) for b in ctx.get("billing_lines") or []]
    gross = round(sum(v for _, v in lines if v and v > 0), 2)
    funding = [(n, -v) for n, v in lines if v and v < 0]
    expected_price = round(total * cfg["blended_rate"], 2)
    if lines and abs(gross - expected_price) > 1:
        warns.append(f"SOW fee {gross:,.2f} differs from loaded hours x rate {expected_price:,.2f}")

    ms = ctx.get("invoicing_milestones") or []
    amts = [money(m.get("amount")) or 0 for m in ms]
    if ms and sum(amts) > 0:
        milestones = [{"description": norm(m.get("milestone")), "percent": round(a / sum(amts) * 100, 4)}
                      for m, a in zip(ms, amts)]
    else:
        milestones = [{"description": d, "percent": float(p)} for d, p in cfg["milestone_default"]]
    milestones[-1]["percent"] = round(100 - sum(m["percent"] for m in milestones[:-1]), 4)

    rp = round(risk_rate * 100, 4)
    allowed = sorted(cfg["risk_field_allowed"])
    below = [a for a in allowed if a <= rp + 1e-9]
    field = below[-1] if below else allowed[0]

    names = " ".join(n.lower() for n, _ in lines)
    pricing = ("Time & material" if re.search(r"t&m|time and material|time & material", names)
               else "Subscription" if re.search(r"recurring|subscription|monthly", names) and "fixed" not in names
               else "Fixed fee")
    details = dict(cfg["details_defaults"])
    details.update({"Customer Name": norm(ctx.get("client_name")), "Pricing Method": pricing,
                    "Project HL Description": " ".join(flatten(ctx.get("project_overview")))[:4000],
                    "Is there funding for the Project": "Yes" if funding else "No"})
    if funding:
        details["AWS funding amount (USD)"] = round(sum(v for _, v in funding), 2)
        details["How many fund request"] = "Only 1" if len(funding) == 1 else "More then 1"
        if len(funding) > 1:
            details["Founding request breakdown"] = "; ".join(f"{n}: {v:,.2f}" for n, v in funding)

    return {
        "version": 1,
        "name": " - ".join(x for x in (norm(ctx.get("client_name")), norm(ctx.get("project_name"))) if x),
        "totals": {"engineering": eng, "pm": pm, "risk": risk, "total_hours": total,
                   "expected_price": expected_price, "fee_gross": gross,
                   "funding_total": round(sum(v for _, v in funding), 2), "customer_total": money(ctx.get("total_price"))},
        "rates": {"pm": pm_rate, "pm_source": pm_src, "risk": risk_rate, "risk_source": risk_src,
                  "blended_rate": cfg["blended_rate"]},
        "columns": {"engineering": ecol, "pm": cfg["pm_column"], "basis": cfg["basis_column_name"]},
        "sections": [s["name"] for s in sections] + [ls],
        "rows": rows,
        "column_totals": column_totals,
        "assumptions": assumptions,
        "exclusions": exclusions,
        "milestones": milestones,
        "milestone_show_dates": bool(cfg["milestone_show_dates"]),
        "risk_field": {"value": f"{field:g}%", "loe_rate": f"{rp:g}%", "mismatch": abs(field - rp) > 1e-9},
        "details": details,
        "basis_column": bool(cfg["basis_column"]),
        "skeleton_policy": cfg["skeleton_policy"],
        "keep_template_rows": cfg["keep_template_rows"],
        "section_refs": cfg["section_refs"],
        "require_crm_link": bool(cfg["require_crm_link"]),
        "warnings": warns + [f"unresolved section reference: {u}" for u in unresolved],
    }


def _inner(d, key):
    d = d or {}
    return d.get(key, d) if isinstance(d, dict) else {}


def check(plan, rb):
    res = []

    def add(code, status, msg, items=None):
        e = {"code": code, "status": status, "msg": msg}
        if items:
            e["items"] = items[:25]
        res.append(e)

    opp = _inner(rb.get("opportunity"), "opportunity")
    bu = _inner(rb.get("bottom_up"), "table")
    cols = [norm(c.get("name")) for c in bu.get("columns", [])]

    def ci(name):
        n = norm(name).lower()
        return next((i for i, c in enumerate(cols) if c.lower() == n), None)

    def cell(c, i):
        return c[i] if i is not None and i < len(c) else None

    T = plan["totals"]
    te, tp = fnum(bu.get("total_effort")), fnum(bu.get("total_price"))
    add("G01", "PASS" if close(te, T["total_hours"], 0.05) else "FAIL",
        f"total effort: Zoma {te} vs plan {T['total_hours']}")
    add("G02", "PASS" if close(tp, T["expected_price"], 1) else "FAIL",
        f"total price: Zoma {tp} vs plan {T['expected_price']}")

    i_show = next((i for i, c in enumerate(cols) if c.lower().startswith("show in")), None)
    i_eff, i_basis = ci("Total Effort"), ci(plan["columns"]["basis"])
    zrows = {}
    for r in bu.get("rows", []):
        c = r.get("cells") or []
        zrows.setdefault(norm(c[0] if c else r.get("name")), []).append(c)
    missing, hours_bad, dup, show_bad, basis_bad = [], [], [], [], []
    for p in plan["rows"]:
        k = norm(p["task"])
        z = zrows.get(k)
        if not z:
            missing.append(k)
            continue
        if len(z) > 1:
            dup.append(k)
        c = z[0]
        if not close(fnum(cell(c, i_eff)), p["hours"], 0.05):
            hours_bad.append(f"{k}: Zoma {cell(c, i_eff)} vs plan {p['hours']}")
        if yes(cell(c, i_show)) != p["show"]:
            show_bad.append(k)
        if plan["basis_column"] and i_basis is not None and norm(cell(c, i_basis)) != norm(p["basis"]):
            basis_bad.append(k)
    bad = [f"missing: {x}" for x in missing] + hours_bad + [f"duplicated: {x}" for x in dup]
    add("G03", "FAIL" if bad else "PASS", f"{len(plan['rows'])} planned rows present with matching hours", bad)
    if plan["basis_column"]:
        if i_basis is None:
            add("G04", "FAIL", f"no {plan['columns']['basis']} column on the Bottom-Up")
        else:
            add("G04", "FAIL" if basis_bad else "PASS", "Basis matches on every planned row", basis_bad)
    if i_show is None:
        add("G05", "FAIL", "no Show in SOW column on the Bottom-Up")
    else:
        add("G05", "FAIL" if show_bad else "PASS", "Show in SOW flags match the plan", show_bad)

    planned = {norm(p["task"]) for p in plan["rows"]}
    extra = [(k, c) for k, cs in zrows.items() if k not in planned for c in cs]
    if plan["skeleton_policy"] == "delete":
        add("G06", "FAIL" if extra else "PASS", f"{len(extra)} rows outside the plan (policy: delete)",
            [k for k, _ in extra])
    else:
        live = [k for k, c in extra if (fnum(cell(c, i_eff)) or 0) != 0 or yes(cell(c, i_show))]
        add("G06", "FAIL" if live else "PASS",
            f"{len(extra)} template rows outside the plan, all at zero hours and hidden" if not live
            else "template rows outside the plan carry hours or show in the SOW", live)

    totals = {norm(t.get("column")): fnum(t.get("value")) for t in bu.get("totals", [])}
    role_bad = [f"{c}: Zoma {totals.get(norm(c))} vs plan {v}" for c, v in plan["column_totals"].items()
                if not close(totals.get(norm(c)), v, 0.05)]
    for c in bu.get("columns", []):
        n = norm(c.get("name"))
        if c.get("type") == "role" and n not in {norm(x) for x in plan["column_totals"]} and (totals.get(n) or 0) != 0:
            role_bad.append(f"{n}: Zoma {totals.get(n)} vs plan 0")
    add("G07", "FAIL" if role_bad else "PASS", "role column totals match the configured split", role_bad)

    risk = None
    for ph in opp.get("detail_phases", []):
        for f in ph.get("fields", []):
            if norm(f.get("name")).lower() == "risk and contingency rate":
                risk = norm((f.get("values") or [""])[0])
    rf = plan["risk_field"]
    if risk is None:
        add("G08", "PASS", "no risk rate field on this opportunity's practice")
    elif risk != rf["value"]:
        add("G08", "FAIL", f"risk field: Zoma {risk} vs plan {rf['value']}")
    elif rf["mismatch"]:
        add("G08", "WARN", f"risk field holds {rf['value']}; the LOE rate is {rf['loe_rate']} and the field cannot carry it")
    else:
        add("G08", "PASS", f"risk field {risk}")

    linked = bool((opp.get("salesforce") or {}).get("linked"))
    add("G09", "PASS" if linked else ("FAIL" if plan["require_crm_link"] else "WARN"),
        "linked to Salesforce" if linked else "not linked to a Salesforce opportunity")

    keep = [re.compile(k, re.I) for k in plan["keep_template_rows"]]
    written = []

    def list_check(code, label, tab, want):
        t = _inner(tab, "table")
        tc = [norm(c.get("name")) for c in t.get("columns", [])]
        si = next((i for i, c in enumerate(tc) if c.lower().startswith("show in")), None)
        visible = [norm(r["cells"][-1]) for r in t.get("rows", [])
                   if r.get("cells") and (si is None or yes(r["cells"][si]))]
        written.extend(visible)
        wanted = [norm(w) for w in want]
        bad = [f"missing: {w}" for w in wanted if w not in visible]
        bad += [f"not in the SOW: {v}" for v in visible if v not in wanted and not any(k.search(v) for k in keep)]
        add(code, "FAIL" if bad else "PASS", f"{label}: {len(wanted)} planned lines visible, no strays", bad)

    list_check("G10", "assumptions", rb.get("assumptions"), plan["assumptions"])
    list_check("G11", "exclusions", rb.get("exclusions"), plan["exclusions"])

    sm = _inner(rb.get("summary"), "summary")
    ms = sm.get("milestones") or []
    ptotal = fnum(sm.get("final_price")) or fnum(sm.get("total_price_after_discount"))
    mbad = []
    if not ms or not ptotal:
        mbad.append("no Summary milestones read back")
    else:
        if len(ms) != len(plan["milestones"]):
            mbad.append(f"count: Zoma {len(ms)} vs plan {len(plan['milestones'])}")
        else:
            for z, p in zip(sorted(ms, key=lambda m: m.get("order", 0)), plan["milestones"]):
                got = (fnum(z.get("amount")) or 0) / ptotal * 100
                if abs(got - p["percent"]) > 0.5:
                    mbad.append(f"{p['description']}: Zoma {got:.1f}% vs plan {p['percent']:g}%")
        if not close(sum(fnum(m.get("amount")) or 0 for m in ms), ptotal, 1):
            mbad.append("milestones do not sum to the project total")
    sd = rb.get("milestones_show_dates")
    if sd is True and not plan["milestone_show_dates"]:
        mbad.append("Show dates is on")
    if mbad:
        add("G12", "FAIL", "payment milestones", mbad)
    elif sd is None:
        add("G12", "WARN", "milestones match; Show dates not read back")
    else:
        add("G12", "PASS", "milestones match, dates off")

    refs = [x for x in list(zrows) + written if REF.search(x)]
    add("G13", ("FAIL" if plan["section_refs"] == "names" else "WARN") if refs else "PASS",
        "no numbered section references in SOW-visible text" if not refs else "numbered section references remain", refs)

    by_type = {}
    for t in opp.get("tabs", []):
        by_type.setdefault(norm(t.get("company_tab_type")), []).append(t)
    dups = [f"{norm(t.get('name'))} ({k})" for k, ts in by_type.items() if len(ts) > 1
            for t in ts if not t.get("is_primary")]
    add("G14", "WARN" if dups else "PASS", "one tab per type" if not dups else "non-primary duplicate tabs", dups)

    vers = _inner(rb.get("sow_versions"), "versions")
    vers = vers if isinstance(vers, list) else []
    if vers:
        newest = max(norm(v.get("created_at")) for v in vers)
        stale = newest < norm(opp.get("updated_at"))
        add("G15", "WARN" if stale else "PASS",
            "newest SOW version predates the last edit" if stale else "newest SOW version is current")
    add("G16", "FAIL" if opp.get("locked") else "PASS", "opportunity unlocked" if not opp.get("locked") else "opportunity is locked")

    fails = [r for r in res if r["status"] == "FAIL"]
    return {"result": "FAIL" if fails else "PASS", "fail": len(fails),
            "warn": len([r for r in res if r["status"] == "WARN"]), "checks": res}


def _fixture(tmp):
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "LOE"
    for row in [
        ["Task", "Hours", "Basis"],
        ["Design", None, None],
        ["Kick-off session", 2, "Meeting, capped at 2h"],
        ["Design document", 16, "8 entities x 2h"],
        ["Build", None, None],
        ["Intake pipeline", 60, "3 sources x 20h"],
        ["Weekly check-in calls", 22, "one call a week over the ceiling"],
        ["Program Management and Risk", None, None],
        ["Project management (10% of engineering effort)", "=ROUND(SUM(B3:B7)*0.1,1)", "10% floor on engineering effort"],
        ["Risk (15% of engineering effort)", "=ROUND(SUM(B3:B7)*0.15,1)", "15%; codebase unread at signing"],
        ["Total loaded hours", "=SUM(B3:B7)+B9+B10", "Engineering plus project management and risk"],
    ]:
        ws.append(row)
    loe = os.path.join(tmp, "LOE.xlsx")
    wb.save(loe)
    ctx = {
        "client_name": "Example Co", "project_name": "Sample Platform",
        "project_overview": {"intro": "Example Co runs a sample platform."},
        "prerequisites": ["Customer grants access within five (5) business days of kick-off"],
        "assumptions": ["Work in Section 2.3.2 depends on the access in Section 2.1"],
        "scope": {"intro": "x", "items": [{"heading": "Design", "bullets": ["a"]}, {"heading": "Build", "bullets": ["b"]}]},
        "exclusions": ["Native mobile applications"],
        "billing_lines": [{"name": "Fixed Fee Project", "price": "$25,000.00"}],
        "total_price": "$25,000.00",
    }
    return ctx, loe


def _readback(plan):
    cols = [{"name": "Type", "type": "text"}, {"name": "Show in the SOW", "type": "dropdown"},
            {"name": "Project Manager", "type": "role"}, {"name": "Engineering", "type": "role"},
            {"name": "Blended Rate US", "type": "role"}, {"name": "Basis", "type": "text"},
            {"name": "Total Effort", "type": "effort"}, {"name": "Total Price", "type": "price"}]
    names = [c["name"] for c in cols]
    rows = [{"cells": ["Template row", "No", "0", "0", "", "", "0", "0"], "section": "Template"}]
    for p in plan["rows"]:
        c = ["", "", "0", "0", "0", "", "", ""]
        c[0], c[1] = p["task"], "Yes" if p["show"] else "No"
        c[names.index(p["column"])] = str(p["hours"])
        c[5], c[6] = p["basis"], str(p["hours"])
        rows.append({"cells": c, "section": p["section"]})
    T = plan["totals"]
    totals = [{"column": n, "value": plan["column_totals"].get(n, 0)} for n in names[2:5]]
    half = T["expected_price"] / 2

    def lst(col, items):
        return {"table": {"columns": [{"name": "Type"}, {"name": "Show in SOW"}, {"name": col}],
                          "rows": [{"cells": ["x", "Yes", i]} for i in items]
                          + [{"cells": ["x", "No", "Template line hidden"]}]}}
    return {
        "opportunity": {"opportunity": {
            "locked": False, "salesforce": {"linked": True}, "updated_at": "2026-01-01T10:00:00.000Z",
            "tabs": [{"name": "Bottom Up", "company_tab_type": "bottom_up", "is_primary": True}],
            "detail_phases": [{"fields": [{"name": "Risk and contingency rate", "values": [plan["risk_field"]["value"]]}]}]}},
        "bottom_up": {"table": {"columns": cols, "totals": totals, "total_effort": str(T["total_hours"]),
                                "total_price": str(T["expected_price"]), "rows": rows}},
        "assumptions": lst("Assumptions", plan["assumptions"]),
        "exclusions": lst("Exclusions", plan["exclusions"] + ["Compliance Certifications: nClouds is not a certifying organization"]),
        "summary": {"summary": {"final_price": str(T["expected_price"]), "milestones": [
            {"order": 1, "description": "Project Kickoff", "amount": half},
            {"order": 2, "description": "Project Completion Sign Off", "amount": half}]}},
        "milestones_show_dates": False,
    }


def selftest():
    cfg = load_config()
    with tempfile.TemporaryDirectory() as tmp:
        ctx, loe = _fixture(tmp)
        plan = build_plan(ctx, loe, cfg)
    T = plan["totals"]
    assert (T["engineering"], T["pm"], T["risk"], T["total_hours"]) == (100.0, 10.0, 15.0, 125.0), T
    assert T["expected_price"] == 25000.0 and plan["warnings"] == [], (T, plan["warnings"])
    assert plan["assumptions"][0] == 'Work in the "Build" scope item depends on the access in the Pre-Requirements section'
    assert plan["assumptions"][1].startswith("Pre-requirement: Customer grants access")
    assert plan["risk_field"] == {"value": "10%", "loe_rate": "15%", "mismatch": True}, plan["risk_field"]
    assert [r["show"] for r in plan["rows"]] == [True, True, True, False, False, False]
    assert plan["column_totals"] == {"Blended Rate US": 125.0}

    def codes(rb, status):
        return {c["code"] for c in check(plan, rb)["checks"] if c["status"] == status}

    good = _readback(plan)
    assert codes(good, "FAIL") == set(), check(plan, good)
    assert codes(good, "WARN") == {"G08"}, codes(good, "WARN")
    cases = {}
    rb = _readback(plan); rb["bottom_up"]["table"]["rows"][2]["cells"][6] = "99"; cases["row hours"] = (rb, {"G03"})
    rb = _readback(plan); rb["bottom_up"]["table"]["rows"][0]["cells"][1] = "Yes"; cases["visible template row"] = (rb, {"G06"})
    rb = _readback(plan); rb["opportunity"]["opportunity"]["salesforce"]["linked"] = False; cases["unlinked"] = (rb, {"G09"})
    rb = _readback(plan); rb["milestones_show_dates"] = True; cases["dates on"] = (rb, {"G12"})
    rb = _readback(plan); rb["assumptions"]["table"]["rows"][-1]["cells"][1] = "Yes"; cases["stray assumption"] = (rb, {"G10"})
    rb = _readback(plan); rb["bottom_up"]["table"]["total_effort"] = "130"; cases["total effort"] = (rb, {"G01"})
    rb = _readback(plan); rb["bottom_up"]["table"]["rows"][1]["cells"][5] = "other"; cases["basis"] = (rb, {"G04"})
    rb = _readback(plan); rb["bottom_up"]["table"]["totals"][1]["value"] = 5; cases["role column"] = (rb, {"G07"})
    rb = _readback(plan); rb["opportunity"]["opportunity"]["locked"] = True; cases["locked"] = (rb, {"G16"})
    for name, (rb, want) in cases.items():
        got = codes(rb, "FAIL")
        assert got == want, f"{name}: expected {want}, got {got}"
    print(f"selftest ok: plan totals, section-reference rewrite, clean gate, {len(cases)} named failures")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--context", required=True)
    p.add_argument("--loe", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--config")
    p.add_argument("--set", action="append", default=[])
    c = sub.add_parser("check")
    c.add_argument("--plan", required=True)
    c.add_argument("--readback", required=True)
    sub.add_parser("selftest")
    a = ap.parse_args()
    if a.cmd == "selftest":
        return selftest()
    if a.cmd == "plan":
        plan = build_plan(json.load(open(a.context)), a.loe, load_config(a.config, a.set))
        json.dump(plan, open(a.out, "w"), indent=1)
        T = plan["totals"]
        print(f"{plan['name']}: {len(plan['rows'])} rows in {len(plan['sections'])} sections, "
              f"{T['engineering']:g}h engineering + {T['pm']:g} PM + {T['risk']:g} risk = {T['total_hours']:g}h, "
              f"price {T['expected_price']:,.2f}; {len(plan['assumptions'])} assumptions, "
              f"{len(plan['exclusions'])} exclusions, {len(plan['milestones'])} milestones; risk field {plan['risk_field']['value']}")
        for w in plan["warnings"]:
            print("WARN:", w)
        return
    out = check(json.load(open(a.plan)), json.load(open(a.readback)))
    print(json.dumps(out, indent=1))
    sys.exit(1 if out["fail"] else 0)


if __name__ == "__main__":
    main()
