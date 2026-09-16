---
name: gmp-access
description: >-
  Plan, review, apply, and audit colleague access changes across Google
  Analytics, Tag Manager, Search Console, and Google Ads. Use for onboarding,
  offboarding, promotion, project access, role changes, or access lookup when
  the request names a person and one of GA/GTM/GSC/Ads.
---

# GMP access

Use the local gmp CLI as the default and only supported programmatic entry point. It references credentials
and resource catalogs from ../GA MCP, ../GTM MCP, ../SEO-Agent, and ../Adwords API
without copying secrets.

The user permits a narrow Chrome fallback when a service account or public API
cannot perform a requested access change. Use YOUR_PRODUCT_ADMIN@example.com only for
product access administration; YOUR_GCP_ADMIN@example.com is for separately requested GCP
service-account lifecycle work. Before fallback, read the project's AGENTS.md and
[identity rules](../../../knowledge/chrome-identities.md), then use the current
Chrome control skill. Neither administrator browser is for reports, ad delivery,
tag publishing, or unrelated content work. Never read browser credential stores,
reuse cookies/tokens, call private Google web APIs, or run legacy UI scripts.
Files under ops/ are dated plans/evidence, not permission to replay operations.

## Establish capability

Run these before a mutation:

    .\.venv\Scripts\gmp.exe doctor
    .\.venv\Scripts\gmp.exe catalog

Use doctor as the live source of truth. Current baseline:

- The user's 2026-09-02 screenshot records
  YOUR_GMP_SA@YOUR_GCP_PROJECT.iam.gserviceaccount.com as directly granted Org Admin,
  User Admin, and Billing Admin in the Your Organization GMP organization. This is
  manual screenshot evidence, not a public-API role lookup.
- gmp_org discovery currently cannot run because the credential project has not
  enabled the GMP Admin API. This does not change the API schema limitation.
- GA reads successfully. YOUR_GMP_SA can read AccessBindings, so doctor reports a
  write candidate as unverified while keeping write=false until a confirmed
  mutation is followed by a successful read-back.
- GTM discovers 14 Your Organization containers from ../GTM MCP; catalog currently maps
  9 of them. The direct GTM permission is Account User; the GMP User Admin
  screenshot makes it a candidate only, not verified product-level write access.
- GSC lists 16 properties at the recorded baseline; CLI personnel changes return
  manual_required. Authorized Chrome follow-up is separate from CLI apply.
- Ads personnel management is pinned to
  YOUR_GMP_SA@YOUR_GCP_PROJECT.iam.gserviceaccount.com. Its direct MCC ADMIN role was
  confirmed through the public API on 2026-09-03. doctor.write=true is an MCC
  role precheck, not proof of every child account's user-management authority or
  a completed mutation.

Administrator OAuth is an available GA/GTM fallback when the selected
product identity lacks sufficient authority:

    .\.venv\Scripts\gmp.exe auth login

OAuth does not create a GSC user-management API or override the Ads personnel
identity. GMP_ADS_CREDENTIALS defaults to the GMP / GTM key path and must belong
to YOUR_GMP_SA. A missing or mismatched key must fail closed. Never fall back to the
ad-serving identity, YAML OAuth, or impersonation. The sibling Adwords API
project must retain YOUR_ADS_SA@YOUR_GCP_PROJECT.iam.gserviceaccount.com and
remain unchanged; this project only reads its developer token and composes a
separate SDK configuration in memory, without copying secrets.

The public Google Marketing Platform Admin API is v1alpha and exposes
organization discovery, Analytics account links, Property usage, and service
levels. It has no users, memberships, roles, or permissions endpoint. Enabling
that API may make this read-only command work, but cannot enable organization
personnel ACL automation:

    .\.venv\Scripts\gmp.exe discover --product gmp-org

CLI employee actions use GA, GTM, and Ads product APIs; GSC remains
manual_required in CLI results. write_candidate/write_unverified never means that write access
has been proven or that a change already happened.

## Interpret the request

Map GA/Analytics to ga, GTM/Tag Manager to gtm, Search Console/SC/GSC to gsc,
and Adwords/Ads to ads. Resolve brands and resource IDs with catalog instead of
guessing.

Use:

- grant or onboard for new access;
- promote for a promotion or new project when access should only increase;
- set-role for an exact role replacement;
- revoke for only the named resources;
- offboard for account-wide GA/GTM removal, all cataloged Ads customers plus
  MCC, and all known GSC sites;
- who for a read-only lookup.

## Create and review an immutable plan

Every mutation command, including a mutation parsed by task, only creates and
saves an immutable plan_id. It must not change Google state.

Natural-language example:

    .\.venv\Scripts\gmp.exe task "把 EMAIL 加入 demo 的 ga gtm sc adwords，按入职只读权限"

Structured example:

    .\.venv\Scripts\gmp.exe grant --email EMAIL --brands demo --products ga,gtm,gsc,ads --preset onboard

Show the user the plan_id, email, operation, products, target roles, resource
IDs, blockers, GSC manual items, privileged actions, and Ads acceptance
requirement. Current state and the idempotent diff are read at apply time and
must be shown in the apply results. The plan cannot be edited. It embeds the
catalog fingerprint, so a catalog.yaml change invalidates it. If the request
changes, make a new plan.

A plan is single-use once a remote execution attempt starts: success, failure,
partial, and unknown outcomes all consume it. Verify current state read-only and
create a new plan instead of replaying it.

For offboard, require the built-in read-only completeness gate before plan
creation and again under the apply lock before claim, audit, or mutation. It
compares GA/GTM account boundaries, GSC site URLs, and the Ads MCC customer
tree. A read failure or either-direction catalog drift must fail closed without
consuming the plan.

This CLI gate does not prove coverage of administrator-visible or historical UI
grants beyond the service account's discovery scope. Before claiming full
offboarding, reconcile that permission inventory and prior API/UI records too.
List UI-only targets in a separate confirmed follow-up; unresolved coverage or
unrevoked items prevent an overall completion claim even if the CLI plan returns
complete=true. Do not bypass its gate or silently expand the confirmed API plan.

Raw --execute on grant/revoke/set-role/onboard/offboard/promote/task is forbidden.

## Apply only after explicit confirmation

After the user explicitly confirms the displayed plan, execute exactly:

    .\.venv\Scripts\gmp.exe apply PLAN_ID --confirm PLAN_ID

GA/GTM/Ads Admin requires --allow-admin during both plan creation and apply:

    .\.venv\Scripts\gmp.exe apply PLAN_ID --confirm PLAN_ID --allow-admin

Do not infer confirmation from the original request. Do not apply a plan after
the user changes any field.

## Preserve operation semantics

- grant/onboard/promote add missing access or raise a lower role; they never
  downgrade a stronger existing role.
- set-role is an exact replacement and requires exactly one product and one
  explicit role. Split a multi-product role change into separate plans.
- revoke removes only the selected resource targets.
- offboard accepts no brand/product scope. It uses account-wide GA/GTM removal,
  all cataloged Ads customers plus MCC, and all known GSC sites. Account-wide
  actions can affect resources not individually listed in catalog.
- GA/GTM/Ads Admin is denied unless the user explicitly requests it and supplies
  the two-stage --allow-admin confirmation. GSC Owner is always blocked by this
  CLI and must be handled manually by an existing Owner.

## Provider-specific truth

GSC Full/Restricted ACL has no official public API. Keep GSC actions in the same
plan with method=manual. On apply they must return manual_required and must never
be counted as success. Do not replace this provider with Site Verification
ownership or browser automation. Separately confirmed Chrome follow-up may
complete the user change without rewriting the original CLI audit as success.

## Authorized Chrome follow-up

- Establish the CLI capability or public API gap first. GSC's absent user ACL API
  is sufficient; do not repeat failed writes to justify browser fallback.
- Verify the visible signed-in email and exact resource's administration rights.
  Profile names or historical administrator claims are not proof.
- Save an immutable UI action list: stable ui_plan_id, actor, target email, action,
  product, actual resource IDs, role, reason, related CLI plan ID if any. A changed
  target needs a new list; never pass this list to gmp apply or edit a consumed plan.
- Show the scope and follow the Chrome skill's action-time confirmation rules.
  Batch unchanged exact items once; extension installation or future fallback
  permission does not confirm a specific access change.
- Preserve grant-only-increases and least privilege. Domain properties include
  subdomains. Missing properties do not authorize creation, ownership verification,
  another account, or broader resources.
- Read back the member and role; where possible verify target-identity API access.
  Report UI success and query verification separately. Inspect uncertain outcomes
  before any retry.
- Save separate final results and append through local feishu-cli to the project's
  designated sheet. Use method=manual and describe Chrome UI plus verified actor.
  Read back the rows; do not overwrite old manual_required records or log previews
  as grants. The project AGENTS.md defines the existing 16-column audit schema.
- Employee offboarding does not imply deleting GCP service accounts, generating
  keys, or changing project IAM. A future dedicated SA-management identity is an
  unimplemented option, not an existing credential or authority.

## Results across execution methods

An Ads invitation is pending_acceptance until the recipient accepts the email.
Report that state instead of saying access is complete.

Cross-product apply is not transactional. Report each product/resource result
separately as ok, skipped, pending_acceptance, manual_required, blocked, partial,
unknown, or error. Never summarize partial or unknown execution as complete.

In apply output, ok=true means no blocked/partial/unknown/error; complete=true
alone means every action is ok/skipped; requires_follow_up=true means manual or
invitation work remains. For partial/unknown, perform read-only checks and never
replay the old plan.

## Audit

After apply, inspect the immutable plan and audit record:

    .\.venv\Scripts\gmp.exe plan PLAN_ID
    .\.venv\Scripts\gmp.exe history --plan-id PLAN_ID

Answer in Chinese unless the user requests another language. Never output .env,
Service Account JSON, developer tokens, OAuth secrets, refresh tokens, or private
keys.
