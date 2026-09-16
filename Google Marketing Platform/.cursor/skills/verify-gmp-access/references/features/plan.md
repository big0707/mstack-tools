# Saved plan

Plan inspection proves the task result was persisted as an immutable, reviewable
artifact.

## Drive

Create and inspect a fresh test plan:

    .\.cursor\skills\verify-gmp-access\control-gmp.ps1 plan

Inspect an existing test plan:

    .\.cursor\skills\verify-gmp-access\control-gmp.ps1 plan -PlanId PLAN_ID

Expected behavior:

- exit code 0 with JSON;
- returned plan_id exactly matches the requested/generated ID;
- actions match the preview count;
- every action includes product, operation, email, role, and resource_id;
- the GSC action remains method=manual.

Inspection must not modify the plan, append audit history, or invoke apply.

The runtime contract additionally binds apply to the catalog SHA-256 captured in
the plan. A later catalog change invalidates the old plan. Once a remote execution
attempt starts, the plan is single-use even when results include failure,
partial, or unknown. This read-only recipe does not exercise consumption; never
invoke apply merely to test it.
