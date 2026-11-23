#!/usr/bin/env python3
"""nclouds-guardrails: one hook script, two events.

  pre     PreToolUse        refuse a tool call that breaks one of the three walls
  prompt  UserPromptSubmit  record a typed send approval for the current turn

Any error exits 0 with no output, so a broken guard never blocks work.
State is one small JSON file on the machine running the session. Nothing is
logged, counted or sent anywhere.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.path.join(os.path.expanduser("~"), ".claude", "nclouds-guardrails")
CAP = 200_000

SEND_OK = re.compile(
    r"\b(send it|send that|send them|send this|go ahead and send|ok(?:ay)? to send|"
    r"approved? to send|yes,? send|send the (?:email|e-mail|message|reply|dm|slack)|"
    r"post it|post that|post this)\b", re.I)
NEGATION = re.compile(r"\b(don'?t|do not|never|not to|without|shouldn'?t|can'?t|cannot|won'?t)\b[^.\n]{0,20}$", re.I)

WRITE_WORDS = ("create", "update", "send", "delete", "trash", "untrash", "copy", "share", "append",
               "insert", "batch_clear", "move", "upload", "request_access")


def load_config():
    with open(os.path.join(HERE, "config.json")) as f:
        return json.load(f)


def state_path(data):
    key = "container" if os.environ.get("CLAUDE_CODE_REMOTE") else (data.get("session_id") or "default")
    key = re.sub(r"[^A-Za-z0-9_.-]", "_", str(key))[:80]
    return os.path.join(STATE_DIR, key + ".json")


def load_state(data):
    try:
        with open(state_path(data)) as f:
            s = json.load(f)
    except Exception:
        s = {}
    s.setdefault("turn", 0)
    s.setdefault("send_ok_turn", -1)
    s.setdefault("reads", {})
    return s


def save_state(data, s):
    os.makedirs(STATE_DIR, exist_ok=True)
    p = state_path(data)
    tmp = p + ".tmp"
    with open(tmp, "w") as f:
        json.dump(s, f)
    os.replace(tmp, p)


def deny(reason):
    json.dump({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": "nclouds-guardrails: " + reason}}, sys.stdout)
    sys.exit(0)


def ids_in(obj, pat, skip=()):
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, (str, int)) and not isinstance(v, bool) and pat.search(k) and k not in skip:
                if str(v).strip():
                    out.append(str(v).strip())
            else:
                out.extend(ids_in(v, pat, skip))
    elif isinstance(obj, list):
        for v in obj:
            out.extend(ids_in(v, pat, skip))
    return out


def is_write(action):
    return any(w in action for w in WRITE_WORDS)


def need_send_ok(s, tool, draft_tool):
    if s["send_ok_turn"] == s["turn"] and s["turn"] > 0:
        return
    deny("%s sends a message, and a send needs the user's typed approval in this turn. Make the draft instead (%s), "
         "tell the user which send is waiting, and stop. The user clears it by typing 'send it'." % (tool, draft_tool))


def pre(data):
    cfg = load_config()
    if not cfg.get("enabled"):
        return
    checks = cfg.get("checks", {})
    tool = data.get("tool_name", "") or ""
    tin = data.get("tool_input", {})
    if not isinstance(tin, dict):
        return
    parts = tool.split("__")
    action = parts[-1].lower()
    server = "__".join(parts[1:-1]).lower() if len(parts) > 2 else ""
    s = load_state(data)

    is_google = bool(re.search(r"google|drive", server)) and "calendar" not in server
    is_rocket = "rocketlane" in server
    if (is_google or is_rocket) and not is_write(action):
        fam = "google" if is_google else "rocketlane"
        s["reads"][fam] = (s["reads"].get(fam, "") + "\n" + json.dumps(tin)[:8000])[-CAP:]
        save_state(data, s)

    if checks.get("sends"):
        if "gmail" in server and action in ("send_message", "reply", "forward"):
            need_send_ok(s, tool, "create_draft")
        if "slack" in server and action in ("slack_send_message", "slack_schedule_message"):
            ch = str(tin.get("channel_id", "")).strip()
            if ch not in cfg.get("slack_send_without_approval", []):
                need_send_ok(s, tool, "slack_send_message_draft")

    if checks.get("drive_read_first") and is_google and is_write(action):
        seen = s["reads"].get("google", "")
        pat = re.compile(r"(?:^|_)(?:file|parent|folder|document|spreadsheet|presentation|doc|sheet)_?id$", re.I)
        for v in ids_in(tin, pat, skip=("pregeneratedId",)):
            if v.lower() == "root":
                continue
            if v not in seen:
                deny("%s touches %s, which has not been read in this session. Read it first (search_files with parentId = '%s' for a folder, "
                     "get_file_metadata or a content read for a file), check what is already there, then repeat this call." % (tool, v, v))

    if checks.get("rocketlane_read_first") and is_rocket and is_write(action):
        seen = s["reads"].get("rocketlane", "")
        pat = re.compile(r"^(?:project|task|phase)Id$")
        for v in ids_in(tin, pat):
            if not re.search(r"(?<!\d)%s(?!\d)" % re.escape(v), seen):
                deny("%s touches Rocketlane id %s, which has not been read in this session. Read it first (get_tasks, get_phases or get_projects "
                     "filtered to %s), check what is already there, then repeat this call." % (tool, v, v))


def prompt(data):
    s = load_state(data)
    s["turn"] += 1
    text = data.get("prompt", "") or ""
    for m in SEND_OK.finditer(text):
        if not NEGATION.search(text[:m.start()]):
            s["send_ok_turn"] = s["turn"]
    save_state(data, s)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "pre"
    data = json.load(sys.stdin)
    {"pre": pre, "prompt": prompt}[mode](data)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        pass
    sys.exit(0)
