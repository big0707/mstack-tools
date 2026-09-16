from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from adwords_agent.config import load_config
from adwords_agent.google_ads import GoogleAdsGateway


@dataclass
class KeywordStats:
    search_term: str
    campaigns: set[str] = field(default_factory=set)
    ad_groups: set[str] = field(default_factory=set)
    paid_impressions: int = 0
    paid_clicks: int = 0
    average_cpc_micros_weighted_sum: int = 0
    organic_impressions: int = 0
    organic_clicks: int = 0
    combined_queries: int = 0
    combined_clicks: int = 0

    @property
    def ctr(self) -> float:
        if not self.paid_impressions:
            return 0.0
        return round(self.paid_clicks / self.paid_impressions * 100, 2)

    @property
    def avg_cpc(self) -> float:
        if not self.paid_clicks:
            return 0.0
        return round(self.average_cpc_micros_weighted_sum / self.paid_clicks / 1_000_000, 2)

    @property
    def seo_priority_score(self) -> float:
        # Simple, explainable score: demand + paid proof + estimated CPC pressure.
        return round(
            self.paid_clicks * 3
            + min(self.avg_cpc, 5) * 10
            + self.paid_impressions / 100,
            2,
        )


def default_start_end() -> tuple[date, date]:
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=92)
    return start, end


def build_query(start: date, end: date, limit: int) -> str:
    return " ".join(
        f"""
        SELECT
          paid_organic_search_term_view.search_term,
          campaign.name,
          ad_group.name,
          segments.search_engine_results_page_type,
          metrics.impressions,
          metrics.clicks,
          metrics.average_cpc,
          metrics.organic_impressions,
          metrics.organic_clicks,
          metrics.combined_queries,
          metrics.combined_clicks
        FROM paid_organic_search_term_view
        WHERE segments.date BETWEEN '{start.isoformat()}' AND '{end.isoformat()}'
          AND segments.search_engine_results_page_type = ADS_ONLY
          AND metrics.impressions > 0
        ORDER BY metrics.impressions DESC
        LIMIT {limit}
        """.split()
    )


def run(customer_id: str, start: date, end: date, limit: int) -> list[KeywordStats]:
    config = load_config()
    gateway = GoogleAdsGateway(config.google_ads_yaml_path, config.google_ads_api_version)
    rows = gateway.search_stream(customer_id=customer_id, query=build_query(start, end, limit))
    grouped: dict[str, KeywordStats] = {}

    for row in rows:
        term = row.paid_organic_search_term_view.search_term.strip()
        stats = grouped.setdefault(term, KeywordStats(search_term=term))
        stats.campaigns.add(row.campaign.name)
        stats.ad_groups.add(row.ad_group.name)
        stats.paid_impressions += int(row.metrics.impressions)
        stats.paid_clicks += int(row.metrics.clicks)
        stats.average_cpc_micros_weighted_sum += int(row.metrics.average_cpc) * int(row.metrics.clicks)
        stats.organic_impressions += int(row.metrics.organic_impressions)
        stats.organic_clicks += int(row.metrics.organic_clicks)
        stats.combined_queries += int(row.metrics.combined_queries)
        stats.combined_clicks += int(row.metrics.combined_clicks)

    return sorted(
        grouped.values(),
        key=lambda item: (
            item.seo_priority_score,
            item.paid_clicks,
            item.paid_impressions,
            item.avg_cpc,
        ),
        reverse=True,
    )


def write_csv(path: Path, items: list[KeywordStats]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "search_term",
                "seo_priority_score",
                "paid_impressions",
                "paid_clicks",
                "paid_ctr_percent",
                "avg_cpc",
                "organic_impressions",
                "organic_clicks",
                "campaigns",
                "ad_groups",
            ]
        )
        for item in items:
            writer.writerow(
                [
                    item.search_term,
                    item.seo_priority_score,
                    item.paid_impressions,
                    item.paid_clicks,
                    item.ctr,
                    item.avg_cpc,
                    item.organic_impressions,
                    item.organic_clicks,
                    "; ".join(sorted(item.campaigns)),
                    "; ".join(sorted(item.ad_groups)),
                ]
            )


def write_markdown(path: Path, items: list[KeywordStats], customer_id: str, start: date, end: date) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    total_impressions = sum(item.paid_impressions for item in items)
    total_clicks = sum(item.paid_clicks for item in items)

    lines = [
        "# SEO 攻词清单：Paid & Organic - Ad shown only",
        "",
        f"- Customer ID: `{customer_id}`",
        f"- Date range: `{start.isoformat()} ~ {end.isoformat()}`",
        f"- Filter: `segments.search_engine_results_page_type = ADS_ONLY`",
        f"- Keywords: `{len(items)}`",
        f"- Paid impressions: `{total_impressions}`",
        f"- Paid clicks: `{total_clicks}`",
        "",
        "## 说明",
        "",
        "这些词在过去 3 个月里有广告展示，但没有自然搜索展示，适合交给 SEO 做内容覆盖、落地页优化或专题页建设。",
        "优先级分数是一个可解释的排序辅助：点击、展示和平均 CPC 越高，越靠前。",
        "",
        "## Top 50",
        "",
        "| Rank | Search term | Score | Impr. | Clicks | CTR | Avg CPC | Campaigns |",
        "| ---: | --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]

    for rank, item in enumerate(items[:50], start=1):
        lines.append(
            "| {rank} | {term} | {score} | {impr} | {clicks} | {ctr}% | {avg_cpc} | {campaigns} |".format(
                rank=rank,
                term=item.search_term.replace("|", "\\|"),
                score=item.seo_priority_score,
                impr=item.paid_impressions,
                clicks=item.paid_clicks,
                ctr=item.ctr,
                avg_cpc=item.avg_cpc,
                campaigns="<br>".join(sorted(item.campaigns)).replace("|", "\\|"),
            )
        )

    lines.extend(
        [
            "",
            "## SEO 处理建议",
            "",
            "- `高点击 + 高 CPC`：优先做核心落地页或专题页，目标是降低长期付费依赖。",
            "- `高展示 + 低点击`：先检查搜索意图，适合做信息型文章、对比页或 FAQ。",
            "- `品牌/竞品词`：单独拆分策略，避免和通用品类词混在同一内容计划里。",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    start_default, end_default = default_start_end()
    parser = argparse.ArgumentParser()
    parser.add_argument("--customer-id", default=load_config().default_customer_id)
    parser.add_argument("--start", default=start_default.isoformat())
    parser.add_argument("--end", default=end_default.isoformat())
    parser.add_argument("--limit", type=int, default=10000)
    parser.add_argument("--out-dir", default="reports")
    args = parser.parse_args()

    if not args.customer_id:
        raise SystemExit("customer_id is required")

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    items = run(args.customer_id, start, end, args.limit)

    suffix = f"{start.isoformat()}_to_{end.isoformat()}"
    out_dir = Path(args.out_dir)
    md_path = out_dir / f"paid_organic_ads_only_seo_keywords_{suffix}.md"
    csv_path = out_dir / f"paid_organic_ads_only_seo_keywords_{suffix}.csv"
    write_markdown(md_path, items, args.customer_id, start, end)
    write_csv(csv_path, items)
    print(f"Markdown: {md_path}")
    print(f"CSV: {csv_path}")
    print(f"Rows: {len(items)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
