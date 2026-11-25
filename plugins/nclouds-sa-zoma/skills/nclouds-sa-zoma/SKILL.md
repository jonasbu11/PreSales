---
name: nclouds-sa-zoma
description: "Push a finished nClouds SOW scope and LOE into Zoma and carry it through to a generated SOW, without changing how the SOW and LOE are built. Four modes. PLAN: map the SOW context and LOE workbook to Zoma's Details fields, Bottom-Up rows, assumptions, exclusions and payment milestones; writes nothing. PUSH: find or create the opportunity and write the plan. CHECK: read everything back and run the gate (hours, price, role columns, risk rate, show-in-SOW flags, leftover template rows, milestones, Salesforce link). FINISH: generate the SOW in the Zoma web app, file it, submit for approval and change status, each outbound step on the SA's go. PM share, risk rate and role columns are configurable. Trigger on 'zoma', 'push to zoma', 'put this SOW in zoma', 'zoma check', 'zoma gate', 'zoma finish', 'generate the SOW in zoma', 'submit to zoma', or /nclouds-sa-zoma. Do NOT trigger for writing an SOW or LOE (nclouds-sa-sow, nclouds-sa-loe), funding-submission SOWs, or Zoma questions that need no opportunity work."
---

# nclouds-sa-zoma

Takes an SOW and LOE that already exist and puts them into Zoma. It never writes scope, never prices, and never changes the SOW or LOE it was given. Funding-submission SOWs are out of scope.

Tool names below are the Zoma connector's (`zoma_...`); the prefix in front of them varies by client. The plugin declares the connector; each SA signs in to Zoma the first time it connects.

## Inputs

1. The SOW `context.json` that nclouds-sa-sow-base-template rendered.
2. The LOE workbook from nclouds-sa-loe (`.xlsx`, sheet `LOE`, columns Task, Hours, Basis, closing loading block).
3. The Salesforce opportunity ID (15 or 18 characters) of the primary opportunity.

Take what is missing from the conversation or the files the SA attached. With no Salesforce ID, stop in one line; the only exception is an explicit test run (`require_crm_link=false`), where the opportunity name ends in ` (test)`.

## Config

`config.json` beside this file holds the defaults. Anything the SA states for this run overrides it (`--set key=value`).

| Key | Default | Meaning |
|---|---|---|
| `pm_rate` | `"loe"` | PM share of engineering hours. `"loe"` takes the rate the LOE states; a number overrides it. `pm_rate_fallback` (0.10) applies when the LOE states none |
| `pm_placement` | `"row"` | `row`: PM is a row whose hours sit in the engineering column. `role_column`: the PM row's hours sit in `pm_column` |
| `risk_rate` | `"loe"` | Same rule as `pm_rate`, with `risk_rate_fallback` (0.10) |
| `risk_field_allowed` | `[0, 5, 10]` | Values Zoma's risk field accepts. The field takes the highest one not above the real rate; a gap is reported, never hidden |
| `engineering_column` | `"Blended Rate US"` | Role column that carries engineering hours |
| `blended_rate` | `200` | Rate used to predict Zoma's price from loaded hours |
| `hour_rounding` | `"none"` | `whole` rounds the PM and risk rows up to whole hours |
| `basis_column` | `true` | Add a Basis text column to the Bottom-Up and fill it |
| `hide_from_sow_patterns` | check-ins, status reports, review cycles, demonstrations, integration QA | Task rows matching these get Show in SOW = No. PM and risk rows are always No |
| `skeleton_policy` | `"hide"` | What happens to the template's own rows: `hide` leaves them at zero hours and out of the SOW; `delete` removes them (permanent) |
| `section_refs` | `"names"` | `names` rewrites "Section 2.x" references to section names, because Zoma's document does not share the base template's numbering |
| `milestone_default`, `milestone_show_dates` | 50/50, `false` | Used when the SOW carries no invoicing schedule. Dates stay off |
| `details_defaults`, `practice_map` | see file | Details values with no source in the SOW, and SOW type to practice fields |
| `require_crm_link`, `max_fix_rounds` | `true`, `2` | Gate strictness on the Salesforce link, and how many fix passes CHECK may drive |

## PLAN (writes nothing)

```bash
python3 scripts/zoma_plan.py plan --context context.json --loe <LOE>.xlsx --out zoma/plan.json [--set key=value ...]
```

It prints the row, hour and price summary and every warning. A warning that the SOW fee differs from loaded hours times the rate goes to the SA before anything is pushed. `plan.json` is the single source for PUSH and CHECK: write from it, never from memory of the SOW.

`python3 scripts/zoma_plan.py selftest` checks the planner and the gate on a built-in example.

## PUSH

Run PLAN first. Then, in order:

1. **Find before create.** `zoma_search_opportunities_by_crm` with the Salesforce ID. An existing opportunity is reused; a second one is never created.
2. **Read the live template.** `zoma_create_opportunity` with `discover_fields: true` (creates nothing). The live list is the authority on names, allowed values and `shown_when` conditions. `references/field-map.md` says where each value comes from.
3. **Create.** `zoma_create_opportunity` with `name` from the plan, `crm_id`, and the Details fields. Pass a parent and the fields it reveals in the same call. A value with no source in the SOW or LOE is left empty unless the field is a blocker; a blocker gets the most defensible value and is named in the report. Never invent a count.
4. **Finish Details.** `zoma_update_opportunity_details` without `updates` lists what is still empty. Fill blockers, preview, confirm. Set the risk field to `plan.risk_field.value`.
5. **Generate the Bottom-Up once.** `zoma_generate_bottom_up`. Every call adds a new tab set, so it runs exactly once per opportunity. If it returns a still-generating tab, read it with `zoma_get_opportunity_tab` until it is done; do not generate again. Work only on the primary tab of each type.
6. **Shape the grid.** Read the Bottom-Up with `granularity: "rows"` and `include_ids: true`. If `basis_column` is on and no Basis column exists, add a text column named per config after the engineering column. For each section in `plan.sections`, in order: `add_section` with the section name (it arrives with one blank row), then `add_row` for each further row.
7. **Fill the grid.** `zoma_update_tab_cells`, batched: task name in the first column, Show in SOW per `plan.rows[].show`, hours in `plan.rows[].column`, Basis. Never write the effort or price columns; Zoma computes them. Then apply `skeleton_policy` to every row that is not in the plan.
8. **Assumptions and Exclusions.** On the primary tab of each: set every template row to Show in SOW = No unless it matches `keep_template_rows`, then add one row per line of `plan.assumptions` and `plan.exclusions` with Show in SOW = Yes.
9. **Milestones.** `zoma_update_milestones` without changes shows the allowed methods and names. Set the custom method with one milestone per `plan.milestones` entry by percent, a name from the allowed list, the plan's description, and Show dates per config. Preview, confirm, and note the Show dates value it returns.
10. Run CHECK.

Write tools that preview first get their preview read before the confirm. Deletes are permanent: say the count before confirming one. Where a generate result's own `how_to_apply` permits an immediate write for the tab it just built, use it exactly as that result describes and nowhere else.

## CHECK

Save each read verbatim as JSON under `zoma/<estimation id>/` and assemble `readback.json`:

```json
{
  "opportunity": <zoma_get_opportunity, detail "full">,
  "bottom_up": <zoma_get_opportunity_tab, primary Bottom-Up, granularity "rows">,
  "assumptions": <zoma_get_opportunity_tab, primary Assumptions, granularity "rows">,
  "exclusions": <zoma_get_opportunity_tab, primary Exclusions, granularity "rows">,
  "summary": <zoma_get_opportunity_tab, Summary, granularity "rows">,
  "sow_versions": <zoma_list_sow_versions, optional>,
  "milestones_show_dates": <true | false | null when not read>
}
```

```bash
python3 scripts/zoma_plan.py check --plan zoma/plan.json --readback zoma/<id>/readback.json
```

| Code | Fails when |
|---|---|
| G01, G02 | Zoma's total effort or total price differs from the plan |
| G03 | A planned row is missing, duplicated, or carries different hours |
| G04, G05 | Basis or Show in SOW differs on a planned row, or the column is absent |
| G06 | A template row outside the plan carries hours or shows in the SOW (`hide`), or exists at all (`delete`) |
| G07 | Role column totals differ from the configured split |
| G08 | The risk field differs from the plan. A rate the field cannot carry is a WARN, expected and reported |
| G09 | Not linked to Salesforce (WARN on a test run) |
| G10, G11 | A planned assumption or exclusion is not visible, or an unplanned line is |
| G12 | Milestone count, split or total is off, or Show dates is on |
| G13 | A numbered section reference survives in SOW-visible text |
| G14, G15 | WARN only: duplicate non-primary tabs; newest SOW version older than the last edit |
| G16 | The opportunity is locked |

On FAIL, fix the cause with the PUSH step that owns it and run CHECK again, up to `max_fix_rounds`. A gate that still fails is reported with its items; FINISH does not run on a failing gate.

## FINISH

Preconditions: the last CHECK passed and nothing was edited since.

1. **Status over the connector first.** `zoma_update_opportunity_details` without `updates` and with `include_non_writable: true`. If Opportunity Status is writable, status changes go through the connector and the browser is needed only for generation.
2. **Browser.** Use the browser the session provides (in Claude Desktop, the built-in browser), open the opportunity's `app_url`. A sign-in page means stop in one line: the sign-in is the SA's. Control labels come from the page as it renders, never from this file. A control that is not on the page is reported with what is there; never guess a neighbor.
3. **Generate the SOW** from the page's export action for this practice. Confirm with `zoma_list_sow_versions` that a version newer than the opportunity's last edit exists.
4. **File it.** `zoma_get_sow_download_link` for that version and fetch the bytes into `zoma/<id>/`. With the Google Drive connector, file it to the client's Presales folder and confirm the size; otherwise deliver the file in the conversation. The link is never printed. A refused fetch is reported in one line with the version id.
5. **Read the generated document** before any status change: fee and hours match the plan, no calendar dates, no template skeleton text, no numbered section references. A defect goes back to PUSH.
6. **Submit for approval.** Outbound: it notifies the approver and copies the account executive. Name the action, take the SA's go, do it, and confirm the status reads as waiting for approval.
7. **Ready for client review**, on a later run once approval is in. Outbound: it attaches the SOW to the Salesforce opportunity, advances its stage and alerts the account executive. Name the action, take the SA's go, do it, confirm the status.

Never move an opportunity to a launched or signed status.

## Report

One block: the opportunity as a link, the mode run, the gate result with every FAIL and WARN item, Details blockers that were filled without a source, and the one action that needs the SA's hand, if any.

## Rules

- `plan.json` is the only source for what gets written.
- No calendar dates anywhere this skill writes. No dollar figures in text fields.
- Generate a Bottom-Up once. Never create a second opportunity for the same Salesforce ID.
- Every status change is outbound and takes the SA's go, each time.
- A count, date, contact or value the SOW and LOE do not state is not written.
