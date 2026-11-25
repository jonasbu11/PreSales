# Zoma Details: where each value comes from

The live field list (`zoma_create_opportunity` with `discover_fields: true`) is the authority on names, allowed values and `shown_when`. This file only says where a value comes from. A field not listed here is left empty unless it is a blocker.

Sources: `ctx` is the SOW `context.json`; `plan` is `plan.json`; `cfg` is the config.

## Basic Info (every opportunity)

| Field | Source |
|---|---|
| Salesforce Opportunity | `crm_id` on the create call, never typed as a field value |
| Customer Name | `plan.details` (from `ctx.client_name`) |
| Pricing Method | `plan.details` (from the billing line names) |
| Core Practice, Sub practice | `cfg.practice_map[<SOW type>]`. A SOW type with no entry stops the push in one line: the practice has no template yet |
| Add-on Practices | Only when the SOW carries a recurring managed-services or resale line |
| Project HL Description | `plan.details` (the SOW's project overview, no dollar figures) |
| Why does the customer want this project? | The Customer's stated need from the project overview or objectives, in the SOW's words. Not composed |
| Is there funding, How many fund request, AWS funding amount, funding breakdown | `plan.details` (from the funding offset billing lines) |
| Country, PM involvement level, funding-wait flag | `cfg.details_defaults` |
| Industry, Company Size | Stated in the session or the client record. Otherwise empty |
| Client signing contact name and role | Stated in the session or the client record. Otherwise empty |
| Estimate due date, Effective Date | Empty. Dates are filled at execution |
| AI Context | Not used by this skill |

## Data & AI (Core Practice = Data & AI)

Zoma uses these counts to drive its own estimate, which the LOE replaces. Fill a count only when the SOW or an LOE Basis states it.

| Field | Source |
|---|---|
| Data & AI solution category | The category the SOW's scope describes. One of the live allowed values |
| Engagement shape | POC, MVP or production, as the SOW's scope definition names it |
| Expected engagement duration (weeks) | The upper bound in `ctx.timeline` |
| New build or extension | The SOW's scope and assumptions |
| Client-facing front-end (mandatory) | Yes when the scope has a user interface item |
| Acceptance standard | Already agreed when `ctx.success_criteria` lists witnessed criteria |
| Number of review cycles | 2, the base template's acceptance line, unless the SOW states otherwise |
| Number of knowledge transfer sessions, training sessions | The count in the scope or the LOE Basis |
| Number of success criteria | Count of `ctx.success_criteria` lines |
| Entity, input type, volume, intake source, tool, read and write system counts | The count an LOE Basis states (`8 entities x 2h`). Otherwise empty |
| Regulated or sensitive data types, SSO | The SOW's assumptions and scope |
| Risk and contingency rate | `plan.risk_field.value` |
| Publicity and reference rights | No unless the SOW grants them |

## MAP Assess (Sub practice = Assess)

| Field | Source |
|---|---|
| SOW Type | MAP-lite Assess or MAP Assess, as the SOW is titled |
| Source environment, Applications / VMs in scope | The SOW's scope |
| Projected 12-mo AWS ARR | The figure the SA states for this deal. Never derived here |
| Assess funding (Partner Cash) | The funding offset billing line |
| AWS Pricing Calculator link | The calculator link for this deal, when one exists |
| Discovery approach, AI modernization in scope | The SOW's scope |
| Out of scope / exclusions | `plan.exclusions`, joined |
| Notes for approvers | Empty |

## MMMO, MSP, Reseller, DevOps

No mapping yet. Fill the mandatory fields from the SOW, leave the rest empty, and name every field filled this way in the report.
