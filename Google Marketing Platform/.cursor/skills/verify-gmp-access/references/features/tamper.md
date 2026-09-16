# Plan tamper refusal

The verifier proves a saved plan cannot be edited after review.

## Drive

    .\.cursor\skills\verify-gmp-access\control-gmp.ps1 tamper

The harness creates a dedicated example.com plan, saves its exact bytes, changes
one local field, and asks gmp plan to load it. Loading must fail with an integrity
or tamper explanation. A finally block restores the original bytes, and the
before/after SHA-256 fingerprint must match.

This recipe never invokes apply. Do not tamper with a real operator plan or an
existing evidence JSON.
