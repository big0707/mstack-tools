from adwords_agent.models import ReportDefinition
from adwords_agent.reports import build_query


def test_build_query_injects_date_range_and_limit() -> None:
    query = build_query(
        ReportDefinition(
            customer_id="123",
            name="daily_campaign",
            date_range="LAST_7_DAYS",
            limit=25,
        )
    )

    assert "DURING LAST_7_DAYS" in query
    assert "LIMIT 25" in query
    assert "\n" not in query


def test_build_change_event_query() -> None:
    query = build_query(
        ReportDefinition(
            customer_id="123",
            name="daily_change_event",
            date_range="YESTERDAY",
            limit=10,
        )
    )

    assert "FROM change_event" in query
    assert "change_event.user_email" in query
    assert "DURING YESTERDAY" in query
