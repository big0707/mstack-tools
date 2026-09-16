from adwords_agent.models import TaskType
from adwords_agent.task_parser import parse_natural_task


def test_parse_report_request() -> None:
    parsed = parse_natural_task("给客户 1234567890 生成昨天广告报告")

    assert parsed.task_type == TaskType.REPORT
    assert parsed.data["customer_id"] == "1234567890"
    assert parsed.data["date_range"] == "YESTERDAY"


def test_parse_create_request_has_missing_copy_fields_note() -> None:
    parsed = parse_natural_task(
        "创建广告，客户 1234567890，广告组 999888777，落地页 https://example.com"
    )

    assert parsed.task_type == TaskType.CREATE_RESPONSIVE_SEARCH_AD
    assert parsed.missing_fields == []
    assert parsed.notes
