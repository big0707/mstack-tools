# Doctor

Doctor performs official read-only checks and reports resource discovery separately
from user-management capability.

## Drive

    .\.cursor\skills\verify-gmp-access\control-gmp.ps1 doctor

Expected behavior:

- exit code 0 with JSON;
- products includes ga, gtm, gsc, ads, and the auxiliary gmp_org item;
- output does not contain private_key, client_secret, or refresh_token;
- read and write/manage.users are reported independently;
- a false write capability includes a useful next_step.
- full `verify` also asserts that `credential_mode=service_account`, the Ads
  provider and identity summary both identify `YOUR_GMP_SA`,
  `write_check_scope=mcc_only`, and `child_write_verified=false`. It does not
  force `write=true`; revoked authority is not a reason to switch identity.

Current baseline is:

- gmp_org read false while the credential project has not enabled the GMP Admin
  API; personnel_user_api and organization_role_api remain false because public
  v1alpha has no users/memberships/roles/permissions endpoint;
- manual screenshot evidence records YOUR_GMP_SA as directly granted Org Admin, User
  Admin, and Billing Admin in Your Organization; this evidence is not API verification;
- GA read true, with AccessBindings readable and write_candidate/write_unverified
  reported while write remains false;
- GTM Your Organization plus 14 containers readable, with direct Account User and an
  unverified write candidate based on the separate organization-role evidence;
- GSC 16 properties/manual only;
- Ads uses the pinned personnel service account
  YOUR_GMP_SA@YOUR_GCP_PROJECT.iam.gserviceaccount.com; its MCC ADMIN role was confirmed
  on 2026-09-03. write=true is only the MCC role precheck, not a live mutation
  test or a guarantee of child-account user-management access. Neither shared
  YAML identity nor general OAuth may override this account. The sibling ad
  serving project retains YOUR_ADS_SA and its configuration unchanged.

The optional read-only discovery command is:

    .\.venv\Scripts\gmp.exe discover --product gmp-org

It can only return organizations and Analytics account links. It cannot list
organization users or roles. API-disabled output does not alter that limitation.

Do not treat a write=false or an authorization 403 from a write probe as a CLI
crash. Do not print credential files while diagnosing it.
