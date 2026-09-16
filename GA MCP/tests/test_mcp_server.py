from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from google.analytics import admin_v1alpha
from pydantic import ValidationError

from ga4_agent.config import Settings
from ga4_agent.mcp_server import (
    AudienceClauseInput,
    AudienceConditionInput,
    DimensionFilterInput,
    OrderByInput,
    _build_audience,
    _dimension_filter_expression,
    _order_bys,
    archive_audience,
    create_audience,
    update_audience,
)


class QueryBuilderTests(unittest.TestCase):
    def test_property_alias_resolution(self) -> None:
        settings = Settings(
            property_id="123456789",
            properties={
                "demo": "123456789",
                "demofour": "123456781",
            },
            credentials_path=None,
        )

        self.assertEqual(settings.resolve_property_name(), "properties/123456789")
        self.assertEqual(
            settings.resolve_property_name("Demofour"),
            "properties/123456781",
        )
        self.assertEqual(
            settings.resolve_property_name("properties/123456782"),
            "properties/123456782",
        )

    def test_multiple_filters_are_anded(self) -> None:
        expression = _dimension_filter_expression(
            [
                DimensionFilterInput(field_name="country", value="China"),
                DimensionFilterInput(
                    field_name="eventName",
                    value="purchase",
                    exclude=True,
                ),
            ]
        )

        self.assertIsNotNone(expression)
        self.assertEqual(len(expression.and_group.expressions), 2)
        self.assertEqual(
            expression.and_group.expressions[0].filter.field_name,
            "country",
        )
        self.assertEqual(
            expression.and_group.expressions[1].not_expression.filter.field_name,
            "eventName",
        )

    def test_order_by_selects_metric_or_dimension(self) -> None:
        orders = _order_bys(
            [
                OrderByInput(field_name="activeUsers"),
                OrderByInput(field_name="country", descending=False),
            ],
            {"activeUsers"},
        )

        self.assertEqual(orders[0].metric.metric_name, "activeUsers")
        self.assertTrue(orders[0].desc)
        self.assertEqual(orders[1].dimension.dimension_name, "country")
        self.assertFalse(orders[1].desc)

    def test_audience_builder_creates_or_group_of_events(self) -> None:
        clause = AudienceClauseInput(
            clause_type="INCLUDE",
            scope="ACROSS_ALL_SESSIONS",
            condition_groups=[
                [
                    AudienceConditionInput(kind="event", event_name="Register"),
                    AudienceConditionInput(kind="event", event_name="Register2"),
                ]
            ],
        )

        audience = _build_audience(
            display_name="Registered users",
            description="Register or Register2",
            membership_duration_days=30,
            filter_clauses=[clause],
        )
        payload = type(audience).to_dict(audience, use_integers_for_enums=False)

        expressions = payload["filter_clauses"][0]["simple_filter"][
            "filter_expression"
        ]["and_group"]["filter_expressions"][0]["or_group"][
            "filter_expressions"
        ]
        self.assertEqual(
            [item["event_filter"]["event_name"] for item in expressions],
            ["Register", "Register2"],
        )

    def test_audience_condition_rejects_missing_value(self) -> None:
        with self.assertRaises(ValidationError):
            AudienceConditionInput(kind="string", field_name="country")

    def test_event_condition_rejects_unused_time_window(self) -> None:
        with self.assertRaises(ValidationError):
            AudienceConditionInput(
                kind="event",
                event_name="Register",
                in_any_n_day_period=30,
            )

    def test_create_audience_preview_never_calls_admin_api(self) -> None:
        clause = AudienceClauseInput(
            condition_groups=[
                [AudienceConditionInput(kind="event", event_name="Register")]
            ]
        )
        with (
            patch(
                "ga4_agent.mcp_server._property_name",
                return_value="properties/123456789",
            ),
            patch("ga4_agent.mcp_server._admin_client") as admin_client,
        ):
            result = create_audience(
                display_name="Preview",
                description="Preview only",
                filter_clauses=[clause],
                confirm=False,
            )

        self.assertFalse(result["created"])
        self.assertTrue(result["requires_confirmation"])
        admin_client.assert_not_called()

    def test_update_audience_preview_does_not_mutate(self) -> None:
        client = MagicMock()
        client.get_audience.return_value = admin_v1alpha.Audience(
            name="properties/123456789/audiences/123",
            display_name="Existing",
            description="Existing description",
            membership_duration_days=30,
        )
        with (
            patch(
                "ga4_agent.mcp_server._audience_name",
                return_value="properties/123456789/audiences/123",
            ),
            patch("ga4_agent.mcp_server._admin_client", return_value=client),
        ):
            result = update_audience(
                audience="123",
                display_name="Proposed",
                confirm=False,
            )

        self.assertFalse(result["updated"])
        self.assertTrue(result["requires_confirmation"])
        client.update_audience.assert_not_called()

    def test_archive_audience_preview_does_not_mutate(self) -> None:
        client = MagicMock()
        client.get_audience.return_value = admin_v1alpha.Audience(
            name="properties/123456789/audiences/123",
            display_name="Existing",
            description="Existing description",
            membership_duration_days=30,
        )
        with (
            patch(
                "ga4_agent.mcp_server._audience_name",
                return_value="properties/123456789/audiences/123",
            ),
            patch("ga4_agent.mcp_server._admin_client", return_value=client),
        ):
            result = archive_audience(audience="123", confirm=False)

        self.assertFalse(result["archived"])
        self.assertTrue(result["requires_confirmation"])
        client.archive_audience.assert_not_called()


if __name__ == "__main__":
    unittest.main()
