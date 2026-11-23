# nclouds-guardrails

Three walls for Claude at work. Each one stops a mistake that is easy to make and awkward to undo.

| Wall | What Claude can no longer do | How you clear it |
|:--|:--|:--|
| No surprise sends | Send, reply to or forward an email, or send or schedule a Slack message, on its own say-so | Type "send it". Claude can always draft. |
| Look before filing | Create, move, rename or share a Drive file or folder it has not looked at in this conversation | Nothing. Claude reads the target and carries on. |
| Look before ticketing | Create or change a Rocketlane task, phase or project it has not looked at in this conversation | Nothing. Claude reads the project and carries on. |

When a wall stops a call, Claude is told exactly which read or which approval clears it. Most of the time you will not notice anything except that the duplicate folder or the early email never happened.

## What it does not do

It collects nothing. There is no log, no count and no report to anyone. The only thing it keeps is a small file, on the machine running the conversation, listing what Claude has read so far.

It does not judge the content of anything. It checks that a send was approved and that a target was read first.

It is a guard against haste, not a security boundary.

## If it gets in your way

If the script fails for any reason, the call goes through. If a wall ever refuses something it should not, remove the plugin and tell the maintainer what Claude was doing.

## Check that it is working

Paste this into a new conversation:

> Email me at my own address, subject "guard test", body "x". Call the Gmail send tool directly, no draft.

Claude should report that the send was refused pending your typed approval. Then type `send it` and the mail goes out.

## Settings

`hooks/config.json` turns each wall on or off. `slack_send_without_approval` takes Slack channel or user ids that Claude may post to without asking, such as your own DM. It ships empty.

## Requirements

Works with the Gmail, Slack, Google Drive, Docs, Sheets, Slides and Rocketlane connectors. Needs `python3` where the session runs, which Claude's cloud sessions and macOS both have.

## Tests

`python3 tests/run.py`
