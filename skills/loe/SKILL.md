---
name: loe
description: "Build a Level of Effort (LOE) Excel workbook listing project tasks with hours per engineering role. Load whenever the user asks for an LOE, level of effort, hours estimate, hours breakdown, engineering hours, role allocation, or wants effort scoped by resource — including standalone requests not paired with an SOW. Produces a single .xlsx file with task rows and role columns, no summary, no totals."
---

# LOE Generator

## When to Use This Skill

Trigger when the user asks for an LOE, level of effort, engineering hours, hours per role, or any breakdown of effort by resource. This skill stands alone — it does not require the sow or sowfunding skills to also be active. The user's notes, transcripts, scope documents, and attached context are the only source of truth for tasks and complexity. Do not invent activities the scope does not support; if a detail is unknown, omit or generalize.

## Output

A single Excel workbook (`.xlsx`) saved to `/mnt/user-data/outputs/` and surfaced through `present_files`. No PDF, no markdown sidecar, no narrative summary in the chat reply beyond a one-line confirmation including total hours. The workbook is the deliverable. The format needs to be very consistent. Include only the required columns. If headers are used for task separation the header should be in the tasks column and not merged.  

Totals may be in a single column on the right side.

## Format

The workbook contains a single sheet named `LOE` with this exact column structure:

```
Task, AI/ML Architect, Cloud Solutions Architect[, Web Developer][, App Developer]
<task name>, <hours>, <hours>[, <hours>][, <hours>]
```

Rules:

- First column is `Task` — the activity description.
- Default role columns are **AI/ML Architect** and **Cloud Solutions Architect**. Every LOE has these two.
- Add **Web Developer** when a web UI, dashboard, customer portal, or browser-based interface is in scope.
- Add **App Developer** when a native mobile or desktop application is in scope.
- Do not add any other roles — no PM, QA, BA, DevOps, Security Architect, or similar — unless the user explicitly requests them by name.
- Do not include a summary row, total row, total column, subtotals, or grand totals. No "LOE Summary" section anywhere in the workbook.
- A role that is not involved in a given task gets `0`, not blank.
- Hours are integers unless half-hours are clearly warranted.

## Hours Discipline

- **Discovery, kickoff, intro, alignment sessions: 1 hour, 2 maximum.** Never more. If the scope tries to inflate discovery, push back and trim.
- **Routine, well-understood tasks** (stock AWS services, common patterns, basic CRUD, standard IAM setup): tight hours.
- **Complex or risky tasks** must be weighted to reflect actual difficulty. Underscoping causes downstream pain. Examples that warrant heavier hours:
  - Custom ML pipelines or non-trivial model selection
  - Ambiguous or shifting requirements
  - Unfamiliar third-party APIs or undocumented integrations
  - HIPAA, SOC 2, FedRAMP, or other compliance overlays
  - Multi-account, cross-region, or hybrid networking
  - Data migration with schema transformation
  - Legacy system reverse engineering
- Resist the urge to assign uniform hours across rows. Real LOEs are uneven.
- Hours for project management and risk will be added later.  They are not required here.

## Pre-Flight Validation

Before generating the workbook, walk through these checks against the scope and the user's stated needs:

1. **Coverage** — does every scope activity have a corresponding task row? Anything missing?
2. **Realism** — are complex tasks weighted heavier than simple ones? Or did everything land suspiciously close to the same number?
3. **Discovery cap** — is every discovery/kickoff/intro task at 1 or 2 hours, no more?
4. **Roles match the work** — Web Developer present only if there is web work; App Developer only if there is app work; neither padded in by default.
5. **Client fit** — does the breakdown reflect what this specific client asked for, or did it drift toward a generic template? Re-read the user's request and confirm alignment.

If any check fails, revise the task list and hours before writing the file.

## File Generation

Use the `xlsx` skill at `/mnt/skills/public/xlsx/SKILL.md` for the openpyxl patterns and conventions in this environment. Read it before writing the workbook.

Workbook conventions:

- Single sheet named `LOE`.
- Header row in bold.
- Column widths auto-sized to content (Task column will typically be the widest).
- Hours columns right-aligned.
- No formulas. No totals. No conditional formatting. No merged cells.
- Save to `/mnt/user-data/outputs/<client-or-project>-LOE.xlsx` — use the client or project name when known; fall back to `LOE.xlsx`.
- Call `present_files` once on the final file path.

## Example

A small Bedrock chatbot POC, AI/ML Architect + Cloud Solutions Architect only:

| Task | AI/ML Architect | Cloud Solutions Architect |
|------|-----------------|---------------------------|
| Discovery and requirements alignment | 1 | 1 |
| AWS account, IAM, and Bedrock model access setup | 0 | 6 |
| Knowledge base data prep and ingestion pipeline | 10 | 8 |
| Bedrock agent and tool definitions | 14 | 2 |
| Prompt engineering and grounding evaluation | 12 | 0 |
| Cognito auth and Amplify chat UI | 0 | 14 |
| End-to-end test scenarios and demo prep | 6 | 4 |
| Documentation and code handoff | 4 | 4 |

Note the unevenness — discovery is a single hour per role, the AI work concentrates on the AI/ML Architect, the auth and infra work concentrates on the Cloud Solutions Architect, and complex steps (ingestion, agent build, prompt tuning) carry more weight than the trivial ones.

## Final Checklist

Before returning the response, verify:

- [ ] Header row is `Task` plus 2 to 4 role columns, no extras.
- [ ] No summary, total, subtotal, or grand-total anywhere in the sheet.
- [ ] Every discovery/kickoff task is at 1 or 2 hours.
- [ ] Complex tasks carry heavier hours than simple ones — distribution is not flat.
- [ ] Roles match the actual scope (no Web/App Developer unless warranted).
- [ ] Tasks map back to what the client actually asked for, not a stock template.
- [ ] File saved to `/mnt/user-data/outputs/` and surfaced via `present_files`.
- [ ] Chat reply is brief — one-line confirmation, no narrative LOE summary.
