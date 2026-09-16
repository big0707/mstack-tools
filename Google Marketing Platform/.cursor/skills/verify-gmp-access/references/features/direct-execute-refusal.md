# Direct execute refusal

Raw mutation --execute must not bypass immutable planning.

## Drive

    .\.cursor\skills\verify-gmp-access\control-gmp.ps1 direct-execute-refusal

Expected behavior:

- the underlying command exits nonzero;
- output identifies --execute as forbidden or unsupported;
- no plan is applied and no audit row is appended.

The harness deliberately combines an invalid email with a nonexistent brand. If
the dedicated refusal guard regresses, ordinary input validation still stops
before any provider call. Do not replace these canary values with a real email or
brand.
