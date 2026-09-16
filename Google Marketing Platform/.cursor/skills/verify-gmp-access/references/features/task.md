# Natural-language task

Task parses a Chinese access request and persists an immutable plan without making
a remote change.

## Drive

    .\.cursor\skills\verify-gmp-access\control-gmp.ps1 task

The harness uses:

    把 verify-gmp-plan@example.com 加入 demo 的 ga gtm gsc ads，按入职只读权限

Expected behavior:

- exit code 0 with JSON;
- parsed email, brand, and all four products are correct;
- dry_run is true;
- plan_id and expires_at are present;
- results is non-empty and no result has status=ok;
- the GSC row has action.method=manual, data.method=manual,
  public_user_api=false, and next_step containing manual_required.

Do not add --execute. Task is a plan generator, not an alternate apply route.
