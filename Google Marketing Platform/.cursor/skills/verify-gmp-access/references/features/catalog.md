# Catalog

Catalog resolves user-facing brand names to explicit GA, GTM, GSC, and Ads resource
IDs without touching Google permissions.

## Drive

    .\.cursor\skills\verify-gmp-access\control-gmp.ps1 catalog

Expected behavior:

- exit code 0 with JSON;
- gmp_organization records organizations/YOUR_GMP_ORG_ID, the three
  screenshot-declared roles, their manual evidence source, and
  roles_verified_by_public_api=false;
- top-level demo exists in the filtered response;
- the response expands product resource identifiers rather than relying on a
  guessed brand name.

Unknown brands must return an actionable error instead of silently selecting
another brand. Resource IDs can change; verify structure and resolution behavior
rather than hard-coding every historical ID in the acceptance script.

The organization evidence is metadata, not an employee ACL target. Do not add
gmp_org to a mutation plan or claim that catalog evidence proves product write
authority.
