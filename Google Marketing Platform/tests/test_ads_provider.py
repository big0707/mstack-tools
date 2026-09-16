from __future__ import annotations

import unittest
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from gmp_access.auth import ADS_PERSONNEL_SERVICE_ACCOUNT
from gmp_access.models import Action, ActionResult
from gmp_access.providers.ads import AdsProvider


MCC_ID = "9000000000"
CHILD_ID = "1000000000"
EMAIL = "colleague@example.com"


class _AccessOperation:
    def __init__(self) -> None:
        self.remove = ""
        self.update = SimpleNamespace(resource_name="", access_role=None)
        self.update_mask = SimpleNamespace(paths=[])


class _InvitationOperation:
    def __init__(self) -> None:
        self.remove = ""
        self.create = SimpleNamespace(email_address="", access_role=None)


class _AccessService:
    def __init__(self, state: dict[str, Any]) -> None:
        self.state = state
        self.calls: list[dict[str, Any]] = []

    def mutate_customer_user_access(self, *, customer_id: str, operation: _AccessOperation) -> None:
        if operation.remove:
            self.calls.append(
                {
                    "kind": "remove",
                    "customer_id": customer_id,
                    "resource_name": operation.remove,
                }
            )
            self.state["users"][customer_id] = [
                item
                for item in self.state["users"].get(customer_id, [])
                if item["resource_name"] != operation.remove
            ]
            return

        self.calls.append(
            {
                "kind": "update",
                "customer_id": customer_id,
                "resource_name": operation.update.resource_name,
                "role": operation.update.access_role,
                "update_mask": list(operation.update_mask.paths),
            }
        )
        for item in self.state["users"].get(customer_id, []):
            if item["resource_name"] == operation.update.resource_name:
                item["role"] = operation.update.access_role
                if self.state.get("raise_after_access_mutation"):
                    raise RuntimeError("simulated connection loss after mutate")
                return
        raise AssertionError("The fake received an update for an unknown Ads user.")


class _InvitationService:
    def __init__(self, state: dict[str, Any]) -> None:
        self.state = state
        self.calls: list[dict[str, Any]] = []

    def mutate_customer_user_access_invitation(
        self,
        *,
        customer_id: str,
        operation: _InvitationOperation,
    ) -> Any:
        if operation.remove:
            self.calls.append(
                {
                    "kind": "remove",
                    "customer_id": customer_id,
                    "resource_name": operation.remove,
                }
            )
            self.state["invitations"][customer_id] = [
                item
                for item in self.state["invitations"].get(customer_id, [])
                if item["resource_name"] != operation.remove
            ]
            return SimpleNamespace(result=SimpleNamespace(resource_name=operation.remove))

        resource_name = (
            f"customers/{customer_id}/customerUserAccessInvitations/"
            f"fake-{len(self.state['invitations'].get(customer_id, [])) + 1}"
        )
        self.calls.append(
            {
                "kind": "create",
                "customer_id": customer_id,
                "email": operation.create.email_address,
                "role": operation.create.access_role,
            }
        )
        self.state["invitations"].setdefault(customer_id, []).append(
            {
                "resource_name": resource_name,
                "email": operation.create.email_address,
                "role": operation.create.access_role,
                "status": "PENDING",
                "customer_id": customer_id,
            }
        )
        return SimpleNamespace(result=SimpleNamespace(resource_name=resource_name))


class _FakeAdsClient:
    def __init__(self, state: dict[str, Any]) -> None:
        self.access_service = _AccessService(state)
        self.invitation_service = _InvitationService(state)
        self.enums = SimpleNamespace(
            AccessRoleEnum=SimpleNamespace(
                ADMIN="ADMIN",
                STANDARD="STANDARD",
                READ_ONLY="READ_ONLY",
                EMAIL_ONLY="EMAIL_ONLY",
            )
        )

    def get_service(self, name: str, *, version: str | None = None) -> Any:
        del version
        if name == "CustomerUserAccessService":
            return self.access_service
        if name == "CustomerUserAccessInvitationService":
            return self.invitation_service
        raise AssertionError(f"Unexpected fake Ads service request: {name}")

    def get_type(self, name: str, *, version: str | None = None) -> Any:
        del version
        if name == "CustomerUserAccessOperation":
            return _AccessOperation()
        if name == "CustomerUserAccessInvitationOperation":
            return _InvitationOperation()
        raise AssertionError(f"Unexpected fake Ads type request: {name}")


class _StatefulAdsProvider(AdsProvider):
    def __init__(
        self,
        *,
        users: dict[str, list[dict[str, Any]]] | None = None,
        invitations: dict[str, list[dict[str, Any]]] | None = None,
        raise_after_access_mutation: bool = False,
    ) -> None:
        settings = SimpleNamespace(
            ads_api_version="v24",
            ads_login_customer_id=MCC_ID,
        )
        super().__init__(settings)
        self.state: dict[str, Any] = {
            "users": users or {},
            "invitations": invitations or {},
            "raise_after_access_mutation": raise_after_access_mutation,
        }
        self.client = _FakeAdsClient(self.state)

    def _client(self) -> _FakeAdsClient:
        return self.client

    def list_users(self, customer_id: str) -> list[dict[str, Any]]:
        return [dict(item) for item in self.state["users"].get(customer_id.replace("-", ""), [])]

    def list_invitations(self, customer_id: str) -> list[dict[str, Any]]:
        return [
            dict(item)
            for item in self.state["invitations"].get(customer_id.replace("-", ""), [])
        ]


def _user(customer_id: str, role: str, *, email: str = EMAIL, suffix: str = "42") -> dict[str, Any]:
    return {
        "resource_name": f"customers/{customer_id}/customerUserAccesses/{suffix}",
        "user_id": int(suffix),
        "email": email,
        "role": role,
        "customer_id": customer_id,
        "access_source": "direct",
    }


def _invitation(
    customer_id: str,
    role: str,
    *,
    status: str = "PENDING",
    suffix: str = "7",
) -> dict[str, Any]:
    return {
        "resource_name": f"customers/{customer_id}/customerUserAccessInvitations/{suffix}",
        "email": EMAIL,
        "role": role,
        "status": status,
        "customer_id": customer_id,
    }


def _action(op: str, role: str | None = None, *, customer_id: str = CHILD_ID) -> Action:
    return Action(
        product="ads",
        op=op,
        email=EMAIL,
        brand="example",
        resource_id=customer_id,
        resource_name=f"Ads customer {customer_id}",
        role=role,
    )


class AdsProviderRegressionTests(unittest.TestCase):
    def test_doctor_checks_personnel_sa_mcc_role_even_with_general_oauth(self) -> None:
        for role, can_write in (("ADMIN", True), ("STANDARD", False), (None, False)):
            with self.subTest(role=role):
                provider = _StatefulAdsProvider()
                users = [_user(MCC_ID, "ADMIN", email="oauth-admin@example.com")]
                if role:
                    users.append(_user(MCC_ID, role, email=ADS_PERSONNEL_SERVICE_ACCOUNT))
                accessible = SimpleNamespace(list_accessible_customers=lambda: SimpleNamespace(resource_names=[f"customers/{MCC_ID}"]))
                with patch("gmp_access.providers.ads.ads_service_account_email", return_value=ADS_PERSONNEL_SERVICE_ACCOUNT), patch(
                    "gmp_access.auth.load_oauth_credentials", side_effect=AssertionError("Ads doctor must not load OAuth")
                ), patch.object(provider, "_service", return_value=accessible), patch.object(
                    provider, "list_customer_tree", return_value=[]
                ), patch.object(provider, "list_users", return_value=users):
                    result = provider.doctor()
                self.assertTrue(result["read"])
                self.assertEqual(result["write"], can_write)
                self.assertEqual(result["credential_email"], ADS_PERSONNEL_SERVICE_ACCOUNT)
                self.assertEqual(result["credential_mode"], "service_account")
                self.assertEqual(result["credential_role"], role or "unknown_or_inherited")
                self.assertEqual(result["write_check_scope"], "mcc_only")
                self.assertFalse(result["child_write_verified"])
                self.assert_no_mutations(provider)

    def assert_no_mutations(self, provider: _StatefulAdsProvider) -> None:
        self.assertEqual(provider.client.access_service.calls, [])
        self.assertEqual(provider.client.invitation_service.calls, [])

    def test_grant_read_only_skips_existing_admin_without_mutation(self) -> None:
        provider = _StatefulAdsProvider(users={CHILD_ID: [_user(CHILD_ID, "ADMIN")]})

        result = provider.apply(_action("grant", "READ_ONLY"), execute=True)

        self.assertEqual(result.status, "skipped")
        self.assertEqual(result.data, {"role": "ADMIN", "access_source": "direct"})
        self.assert_no_mutations(provider)

    def test_same_pending_invitation_is_not_sent_twice(self) -> None:
        pending = _invitation(CHILD_ID, "READ_ONLY")
        provider = _StatefulAdsProvider(invitations={CHILD_ID: [pending]})

        result = provider.apply(_action("grant", "READ_ONLY"), execute=True)

        self.assertEqual(result.status, "pending_acceptance")
        self.assertEqual(result.data["resource_name"], pending["resource_name"])
        self.assert_no_mutations(provider)

    def test_revoke_removes_active_access_and_pending_invitation(self) -> None:
        active = _user(CHILD_ID, "STANDARD")
        pending = _invitation(CHILD_ID, "READ_ONLY", suffix="8")
        expired = _invitation(CHILD_ID, "READ_ONLY", status="EXPIRED", suffix="9")
        provider = _StatefulAdsProvider(
            users={CHILD_ID: [active]},
            invitations={CHILD_ID: [pending, expired]},
        )

        result = provider.apply(_action("revoke"), execute=True)

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.data["removed"], ["active_access", "pending_invitation"])
        self.assertEqual(provider.list_users(CHILD_ID), [])
        self.assertEqual(provider.list_invitations(CHILD_ID), [expired])
        self.assertEqual(
            provider.client.access_service.calls,
            [
                {
                    "kind": "remove",
                    "customer_id": CHILD_ID,
                    "resource_name": active["resource_name"],
                }
            ],
        )
        self.assertEqual(
            provider.client.invitation_service.calls,
            [
                {
                    "kind": "remove",
                    "customer_id": CHILD_ID,
                    "resource_name": pending["resource_name"],
                }
            ],
        )

    def test_set_role_can_downgrade_where_grant_cannot(self) -> None:
        target = _user(CHILD_ID, "ADMIN")
        break_glass = _user(
            CHILD_ID,
            "ADMIN",
            email="break-glass@example.com",
            suffix="99",
        )
        provider = _StatefulAdsProvider(users={CHILD_ID: [target, break_glass]})

        grant_result = provider.apply(_action("grant", "READ_ONLY"), execute=True)

        self.assertEqual(grant_result.status, "skipped")
        self.assert_no_mutations(provider)

        set_role_result = provider.apply(_action("set_role", "READ_ONLY"), execute=True)

        self.assertEqual(set_role_result.status, "ok")
        self.assertEqual(set_role_result.data, {"role": "READ_ONLY", "verified": True})
        self.assertEqual(provider.list_users(CHILD_ID)[0]["role"], "READ_ONLY")
        self.assertEqual(
            provider.client.access_service.calls,
            [
                {
                    "kind": "update",
                    "customer_id": CHILD_ID,
                    "resource_name": target["resource_name"],
                    "role": "READ_ONLY",
                    "update_mask": ["access_role"],
                }
            ],
        )
        self.assertEqual(provider.client.invitation_service.calls, [])

    def test_child_set_role_is_blocked_by_higher_inherited_mcc_access(self) -> None:
        provider = _StatefulAdsProvider(users={MCC_ID: [_user(MCC_ID, "ADMIN")]})

        result = provider.apply(_action("set_role", "READ_ONLY"), execute=True)

        self.assertEqual(result.status, "blocked")
        self.assertIn("MCC", result.message)
        self.assertIn("先单独调整 MCC 权限", result.next_step)
        self.assert_no_mutations(provider)

    def test_inherited_mcc_access_blocks_child_revoke_even_with_direct_access(self) -> None:
        provider = _StatefulAdsProvider(
            users={
                MCC_ID: [_user(MCC_ID, "ADMIN")],
                CHILD_ID: [_user(CHILD_ID, "READ_ONLY")],
            }
        )

        result = provider.apply(_action("revoke"), execute=True)

        self.assertEqual(result.status, "blocked")
        self.assertIn("仍通过 MCC 继承", result.message)
        self.assertEqual(provider.list_users(CHILD_ID)[0]["role"], "READ_ONLY")
        self.assert_no_mutations(provider)

    def test_inherited_mcc_access_blocks_child_downgrade_with_direct_access(self) -> None:
        provider = _StatefulAdsProvider(
            users={
                MCC_ID: [_user(MCC_ID, "ADMIN")],
                CHILD_ID: [_user(CHILD_ID, "STANDARD")],
            }
        )

        result = provider.apply(_action("set_role", "READ_ONLY"), execute=True)

        self.assertEqual(result.status, "blocked")
        self.assertIn("MCC", result.message)
        self.assertEqual(provider.list_users(CHILD_ID)[0]["role"], "STANDARD")
        self.assert_no_mutations(provider)

    def test_inherited_mcc_access_satisfies_grant_without_direct_update(self) -> None:
        provider = _StatefulAdsProvider(
            users={
                MCC_ID: [_user(MCC_ID, "ADMIN")],
                CHILD_ID: [_user(CHILD_ID, "READ_ONLY")],
            }
        )

        result = provider.apply(_action("grant", "STANDARD"), execute=True)

        self.assertEqual(result.status, "skipped")
        self.assertEqual(result.data, {"access_source": "inherited_mcc", "role": "ADMIN"})
        self.assertEqual(provider.list_users(CHILD_ID)[0]["role"], "READ_ONLY")
        self.assert_no_mutations(provider)

    def test_set_role_downgrades_higher_direct_access_when_mcc_matches_target(self) -> None:
        provider = _StatefulAdsProvider(
            users={
                MCC_ID: [_user(MCC_ID, "READ_ONLY")],
                CHILD_ID: [
                    _user(CHILD_ID, "ADMIN"),
                    _user(
                        CHILD_ID,
                        "ADMIN",
                        email="break-glass@example.com",
                        suffix="99",
                    ),
                ],
            }
        )

        result = provider.apply(_action("set_role", "READ_ONLY"), execute=True)

        self.assertEqual(result.status, "ok")
        self.assertEqual(provider.list_users(CHILD_ID)[0]["role"], "READ_ONLY")
        self.assertEqual(len(provider.client.access_service.calls), 1)
        self.assertEqual(provider.client.access_service.calls[0]["kind"], "update")

    def test_set_role_clears_higher_pending_invitation_when_mcc_matches_target(self) -> None:
        pending = _invitation(CHILD_ID, "ADMIN")
        provider = _StatefulAdsProvider(
            users={MCC_ID: [_user(MCC_ID, "READ_ONLY")]},
            invitations={CHILD_ID: [pending]},
        )

        result = provider.apply(_action("set_role", "READ_ONLY"), execute=True)

        self.assertEqual(result.status, "ok")
        self.assertEqual(provider.list_invitations(CHILD_ID), [])
        self.assertEqual(len(provider.client.invitation_service.calls), 1)
        self.assertEqual(provider.client.invitation_service.calls[0]["kind"], "remove")

    def test_set_role_refuses_to_downgrade_last_direct_admin(self) -> None:
        provider = _StatefulAdsProvider(users={CHILD_ID: [_user(CHILD_ID, "ADMIN")]})

        result = provider.apply(_action("set_role", "READ_ONLY"), execute=True)

        self.assertEqual(result.status, "blocked")
        self.assertIn("最后一位", result.message)
        self.assertEqual(provider.list_users(CHILD_ID)[0]["role"], "ADMIN")
        self.assert_no_mutations(provider)

    def test_mcc_action_runs_before_child_for_set_role(self) -> None:
        provider = _StatefulAdsProvider()
        child = _action("set_role", "READ_ONLY")
        mcc = _action("set_role", "READ_ONLY", customer_id=MCC_ID)
        mcc.details["scope"] = "mcc"
        order: list[str] = []

        def record(target: Action, *, execute: bool) -> ActionResult:
            self.assertTrue(execute)
            order.append(target.resource_id)
            return ActionResult(target, "skipped", False, "recorded")

        with patch.object(provider, "apply", side_effect=record):
            provider.apply_many([child, mcc], execute=True)

        self.assertEqual(order, [MCC_ID, CHILD_ID])

    def test_post_mutation_exception_is_reported_as_unknown(self) -> None:
        provider = _StatefulAdsProvider(
            users={CHILD_ID: [_user(CHILD_ID, "STANDARD")]},
            raise_after_access_mutation=True,
        )

        result = provider.apply(_action("set_role", "READ_ONLY"), execute=True)

        self.assertEqual(result.status, "unknown")
        self.assertIn("最终状态无法验证", result.message)
        self.assertEqual(provider.list_users(CHILD_ID)[0]["role"], "READ_ONLY")


if __name__ == "__main__":
    unittest.main()
