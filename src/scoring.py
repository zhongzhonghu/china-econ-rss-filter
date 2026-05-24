"""
scoring.py — 计算最终优先级分数，决定 final_keep。
"""
import logging
from datetime import datetime, timezone

from .database import Database

logger = logging.getLogger(__name__)

# 权重（spec §9.2）
W_CHINA = 0.25
W_ECON = 0.20
W_EXPERT = 0.20
W_ORIG = 0.15
W_SOURCE = 0.10
W_FRESH = 0.10
W_NOISE = -0.25

FRESHNESS_MAX_HOURS = 168  # 7 天


def compute_all_scores(db: Database) -> dict:
    """
    对所有 rule_keep=1 的文章计算 final_priority_score 和 final_keep。
    """
    articles = db.conn.execute(
        "SELECT * FROM articles WHERE rule_keep = 1"
    ).fetchall()

    kept = 0
    rejected = 0

    for row in articles:
        article = dict(row)
        score, level = compute_priority_score(article)
        keep = apply_keep_rule(article)

        db.update_article(
            article["id"],
            final_priority_score=round(score, 4),
            priority_level=level,
            final_keep=1 if keep else 0,
        )

        if keep:
            kept += 1
        else:
            rejected += 1

    # 对 rule_keep=0 的文章也设置 final_keep=0（避免遗漏）
    db.conn.execute(
        "UPDATE articles SET final_keep = 0 WHERE rule_keep = 0 AND final_keep IS NULL"
    )
    db.conn.commit()

    logger.info(f"scoring: {kept} kept, {rejected} rejected")
    return {"kept": kept, "rejected": rejected}


def compute_priority_score(article: dict) -> tuple[float, str]:
    """
    返回 (priority_score, priority_level)。
    """
    china = _f(article.get("china_relevance_score"))
    econ = _f(article.get("economic_relevance_score"))
    expert = _f(article.get("expert_or_fact_score"))
    orig = _f(article.get("originality_score"), default=0.5)
    source = _f(article.get("source_quality_score"), default=0.5)
    noise = _f(article.get("noise_score"))
    fresh = freshness_score(article.get("published_at"))

    score = (
        W_CHINA * china
        + W_ECON * econ
        + W_EXPERT * expert
        + W_ORIG * orig
        + W_SOURCE * source
        + W_FRESH * fresh
        + W_NOISE * noise
    )
    score = max(0.0, min(1.0, score))

    if score >= 0.75:
        level = "High"
    elif score >= 0.55:
        level = "Medium"
    else:
        level = "Low"

    return score, level


def apply_keep_rule(article: dict) -> bool:
    """
    spec §9.1 保留规则。
    """
    china = _f(article.get("china_relevance_score"))
    econ = _f(article.get("economic_relevance_score"))
    noise = _f(article.get("noise_score"))
    expert = _f(article.get("expert_or_fact_score"))
    has_expert = bool(article.get("has_expert_opinion"))
    has_fact = bool(article.get("has_latest_economic_fact"))

    return (
        china >= 0.65
        and econ >= 0.60
        and noise <= 0.40
        and (expert >= 0.60 or has_expert or has_fact)
    )


def freshness_score(published_at: str) -> float:
    """
    24h 内 = 1.0，线性衰减到 7天 = 0.0。
    """
    if not published_at:
        return 0.5
    try:
        dt = _parse_dt(published_at)
        now = datetime.now(timezone.utc)
        age_hours = (now - dt).total_seconds() / 3600
        if age_hours <= 24:
            return 1.0
        elif age_hours >= FRESHNESS_MAX_HOURS:
            return 0.0
        else:
            return 1.0 - (age_hours - 24) / (FRESHNESS_MAX_HOURS - 24)
    except Exception:
        return 0.5


def _parse_dt(s: str) -> datetime:
    """解析 ISO 8601 字符串（带或不带时区）。"""
    s = s.strip()
    # 处理 "+00:00" 格式
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        pass
    # 尝试无时区格式（当作 UTC）
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s[:len(fmt)], fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse date: {s}")


def _f(val, default: float = 0.0) -> float:
    try:
        return float(val) if val is not None else default
    except (TypeError, ValueError):
        return default
