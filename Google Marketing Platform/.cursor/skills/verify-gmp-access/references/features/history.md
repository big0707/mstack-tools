# History

History exposes local JSONL audit records without creating a new record.

## Drive

    .\.cursor\skills\verify-gmp-access\control-gmp.ps1 history

Expected behavior:

- exit code 0 with JSON;
- ok is true;
- an empty history is valid;
- existing rows remain unchanged;
- output contains no token, client secret, private key, or credential content.

The complete verifier fingerprints .data/audit.jsonl before and after all checks.
The fingerprints must match because verification never invokes apply.

When reviewing existing apply records, preserve the exact item states: ok,
skipped, pending_acceptance, manual_required, blocked, partial, unknown, and
error. complete=true requires every item to be ok/skipped. A consumed plan with
partial/unknown results must be read-only verified and replaced with a new plan,
never replayed.
