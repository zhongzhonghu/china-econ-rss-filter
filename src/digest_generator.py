"""
digest_generator.py — 生成每日摘要 Markdown 和 CSV。
"""
import csv
import logging
from collections import defaultdict
from datetime import datetime

from . import config_loader
from .database import Database

logger = logging.getLogger(__name__)


def generate_digest(db: Database) -> dict:
    """
    生成 output/daily_digest.md 和 output/selected_articles.csv。
    """
    topics = config_loader.load_topics()
    articles = db.get_all_kept_articles()

    output_dir = config_loader.OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    digest_path = output_dir / "daily_digest.md"
    csv_path = output_dir / "selected_articles.csv"

    _write_digest_md(digest_path, articles, topics)
    _write_csv(csv_path, articles)

    logger.info(f"Digest: {len(articles)} articles → {digest_path}")
    return {"article_count": len(articles), "digest_path": str(digest_path)}


def _write_digest_md(path, articles: list, topics: dict):
    today = datetime.now().strftime("%Y-%m-%d")
    lines = [
        f"# 中国经济精选每日摘要 — {today}",
        "",
        f"**共保留文章：{len(articles)} 篇**",
        "",
    ]

    if not articles:
        lines.append("_今日无符合标准的文章。_")
        path.write_text("\n".join(lines), encoding="utf-8")
        return

    # 统计概要
    high = sum(1 for a in articles if a.get("priority_level") == "High")
    med = sum(1 for a in articles if a.get("priority_level") == "Medium")
    low = sum(1 for a in articles if a.get("priority_level") == "Low")
    lines += [
        f"- 高优先级：{high} 篇",
        f"- 中优先级：{med} 篇",
        f"- 低优先级：{low} 篇",
        "",
        "---",
        "",
    ]

    # 按主题分组
    by_topic = defaultdict(list)
    for a in articles:
        topic = a.get("primary_topic") or "T00"
        by_topic[topic].append(a)

    for topic_id in sorted(by_topic.keys()):
        label = topics.get(topic_id, topic_id)
        group = sorted(
            by_topic[topic_id],
            key=lambda x: x.get("final_priority_score") or 0,
            reverse=True,
        )
        lines.append(f"## {topic_id} {label}")
        lines.append("")
        for a in group:
            score = a.get("final_priority_score") or 0
            level = a.get("priority_level") or "Low"
            title = a.get("title") or "（无标题）"
            url = a.get("url") or ""
            source = a.get("source") or ""
            summary = a.get("llm_summary") or a.get("rss_summary") or ""
            reason = a.get("reason_for_keep") or ""

            lines.append(f"### [{title}]({url})")
            lines.append(f"**来源：** {source} | **优先级：** {level} ({score:.2f})")
            if summary:
                lines.append(f"> {summary[:200]}")
            if reason:
                lines.append(f"_保留原因：{reason[:150]}_")
            lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def _write_csv(path, articles: list):
    if not articles:
        path.write_text("", encoding="utf-8")
        return

    fieldnames = [
        "title", "url", "source", "source_type", "author", "published_at",
        "primary_topic", "secondary_topics", "priority_level", "final_priority_score",
        "china_relevance_score", "economic_relevance_score", "expert_or_fact_score",
        "originality_score", "noise_score", "has_expert_opinion", "has_latest_economic_fact",
        "llm_summary", "reason_for_keep",
    ]

    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for a in articles:
            writer.writerow({k: a.get(k, "") for k in fieldnames})

    logger.info(f"Written CSV: {path}")
