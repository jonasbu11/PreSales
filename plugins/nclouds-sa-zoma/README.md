# nclouds-sa-zoma

Gets a finished SOW and LOE into Zoma without retyping them. You build the scope and the hours the way you do now; this plugin writes them into the Zoma opportunity, checks that Zoma holds what you built, and walks the opportunity through SOW generation and approval.

It never writes scope and never prices. It moves what you already decided.

## What you need

- A finished SOW: the `context.json` the base template rendered from (nclouds-sa-sow produces it).
- The LOE workbook from nclouds-sa-loe: sheet `LOE`, columns Task, Hours and Basis, ending with the Program Management and Risk block.
- The Salesforce opportunity ID (15 or 18 characters) of the primary opportunity.
- A Zoma login. The plugin declares the Zoma connector; the first time it connects, Zoma asks you to sign in.
- For the last stage only, a browser the session can drive (in Claude Desktop, the built-in browser) signed in to Zoma.

Funding-submission SOWs are out of scope.

## How it works

Four steps. You can run any one on its own.

| Step | What happens | Writes to Zoma? |
|:--|:--|:--|
| Plan | Reads the SOW and the LOE and works out every value that will go into Zoma: Details fields, Bottom-Up rows with hours and Basis, assumptions, exclusions, payment milestones. Prints the totals and any warnings, such as the fee not matching loaded hours times the rate. | No |
| Push | Finds the opportunity by Salesforce ID, or creates it if none exists. Fills Details, generates the Bottom-Up once, adds your sections and rows, hides the template's own rows, writes assumptions, exclusions and milestones. | Yes |
| Check | Reads everything back from Zoma and compares it to the plan. Fails on wrong hours or price, missing or extra rows, role columns that do not match the split, a wrong risk field, template rows showing in the SOW, milestones off or dated, no Salesforce link, or "Section 2.x" references left in SOW text. | No |
| Finish | Generates the SOW in the Zoma web app, files the document, then submits for approval and later moves the opportunity to ready for client review. | Yes |

The plan is the single source for everything written. Nothing is typed into Zoma from memory of the SOW.

Ask for it in plain words: "push this SOW to Zoma", "zoma check", "zoma finish". Give it the files and the Salesforce ID.

## What asks you first

Anything that leaves Zoma waits for you to say go, every time:

- Submitting for approval notifies the approver and copies the AE.
- Moving to ready for client review attaches the SOW to the Salesforce opportunity, advances its stage and alerts the AE.

It never moves an opportunity to launched or signed. Deleting rows from Zoma is permanent, so the count is stated before any delete.

## What it will not do

- Invent a value. A count, date, contact or figure the SOW and LOE do not state stays empty, unless Zoma refuses to continue without it; then the value it used is named in the report.
- Create a second opportunity for the same Salesforce ID, or generate a second Bottom-Up on the same opportunity.
- Put calendar dates on milestones.
- Run Finish on an opportunity that failed Check.

## Settings

`skills/nclouds-sa-zoma/config.json`. Anything you say for one run overrides it for that run.

| Setting | Default | What it controls |
|:--|:--|:--|
| `pm_rate` | `"loe"` | PM hours as a share of engineering. `"loe"` uses the rate your LOE states; 10% if it states none |
| `pm_placement` | `"row"` | PM as its own row in the engineering column, or in Zoma's Project Manager column (`"role_column"`) |
| `risk_rate` | `"loe"` | Same rule as PM. Zoma's risk field only accepts 0, 5 or 10%; a higher rate is written to the row in full and the gap is reported |
| `engineering_column` | `"Blended Rate US"` | Which Zoma role column carries engineering hours |
| `blended_rate` | `200` | Rate used to predict the price Zoma should show |
| `hour_rounding` | `"none"` | `"whole"` rounds PM and risk up to whole hours |
| `skeleton_policy` | `"hide"` | Zoma's template rows: hidden at zero hours, or deleted (`"delete"`) |
| `hide_from_sow_patterns` | check-ins, status reports, review cycles, demos, integration QA | Rows that stay in the estimate but out of the SOW text |

## Layout

```
.mcp.json                                Zoma connector
skills/nclouds-sa-zoma/SKILL.md          the steps Claude follows
skills/nclouds-sa-zoma/config.json       settings above
skills/nclouds-sa-zoma/references/field-map.md   where each Zoma Details value comes from
skills/nclouds-sa-zoma/scripts/zoma_plan.py      plan and check
```

## Status

Version 0.1.0, out for feedback. Plan and Check are tested. Push and Finish follow the Zoma connector's tool definitions and the nClouds Zoma manual, and have not yet run against a live opportunity. The first real one will find what they miss.

Zoma's practice templates decide what Details asks for. Data & AI and MAP Assess are mapped; MMMO, MSP, Reseller and DevOps fill only what Zoma requires.

## Tests

`python3 skills/nclouds-sa-zoma/scripts/zoma_plan.py selftest`
