"""
rule_filter.py — 关键词规则过滤，对每篇文章打分并决定 rule_keep。
"""
import re
import logging

from . import config_loader
from .database import Database

logger = logging.getLogger(__name__)

EXPERT_PATTERN = re.compile(
    r"[\u4e00-\u9fff]{2,4}(?:认为|表示|指出|称|强调|建议|分析|预计|判断|指)"
)
DATA_PATTERN = re.compile(r"\d+(?:\.\d+)?(?:%|百分点|亿|万亿|万|千亿|bp)")


def run_rule_filter(db: Database) -> dict:
    """
    对所有 final_keep IS NULL 且 rule_keep IS NULL 的文章施加规则。
    返回统计信息。
    """
    rules = config_loader.load_filter_rules()
    articles = db.conn.execute(
        "SELECT * FROM articles WHERE rule_keep IS NULL AND final_keep IS NULL"
    ).fetchall()

    total = 0
    kept = 0
    rejected = 0

    for row in articles:
        article = dict(row)
        result = apply_rules(article, rules)

        db.update_article(
            article["id"],
            rule_keep=1 if result["rule_keep"] else 0,
            rule_reject_reason=result.get("rule_reject_reason", ""),
            china_relevance_score=result["china_relevance_score"],
            economic_relevance_score=result["economic_relevance_score"],
            originality_score=result["originality_score"],
            noise_score=result["noise_score"],
            expert_or_fact_score=result["expert_or_fact_score"],
            has_expert_opinion=1 if result["has_expert_opinion"] else 0,
            has_latest_economic_fact=1 if result["has_latest_economic_fact"] else 0,
        )

        total += 1
        if result["rule_keep"]:
            kept += 1
        else:
            rejected += 1

    logger.info(f"rule_filter: {total} processed, {kept} kept, {rejected} rejected")
    return {"total": total, "kept": kept, "rejected": rejected}


def apply_rules(article: dict, rules: dict) -> dict:
    """
    计算各维度分数，决定是否保留。
    返回包含所有分数和 rule_keep 的字典。
    """
    text = _build_text(article)

    china_score = _keyword_score(text, rules.get("china_keywords", []))
    econ_score = _keyword_score(text, rules.get("economic_keywords", []))
    noise_score = _keyword_score(text, rules.get("noise_keywords", []))
    originality_score = _originality_score(text, rules)
    expert_score, has_expert, has_fact = _expert_and_fact_score(text)

    source_quality = float(article.get("source_quality_score") or 0.5)

    # 保留条件（spec 9.1）
    base_keep = (
        china_score >= 0.65
        and econ_score >= 0.60
        and noise_score <= 0.40
        and (expert_score >= 0.60 or has_expert or has_fact)
    )
    # 高质量来源豁免（部分放宽）
    trusted_keep = source_quality >= 0.80 and china_score >= 0.40 and econ_score >= 0.40

    rule_keep = base_keep or trusted_keep

    reject_reason = ""
    if not rule_keep:
        reasons = []
        if china_score < 0.65:
            reasons.append(f"china_score={china_score:.2f}<0.65")
        if econ_score < 0.60:
            reasons.append(f"econ_score={econ_score:.2f}<0.60")
        if noise_score > 0.40:
            reasons.append(f"noise_score={noise_score:.2f}>0.40")
        if not (expert_score >= 0.60 or has_expert or has_fact):
            reasons.append("no expert/fact signal")
        reject_reason = "; ".join(reasons)

    return {
        "rule_keep": rule_keep,
        "rule_reject_reason": reject_reason,
        "china_relevance_score": round(china_score, 4),
        "economic_relevance_score": round(econ_score, 4),
        "originality_score": round(originality_score, 4),
        "noise_score": round(noise_score, 4),
        "expert_or_fact_score": round(expert_score, 4),
        "has_expert_opinion": has_expert,
        "has_latest_economic_fact": has_fact,
    }


# ─── Internal helpers ────────────────────────────────────────────────────────

def _build_text(article: dict) -> str:
    parts = [
        article.get("title") or "",
        article.get("rss_summary") or "",
        article.get("cleaned_text") or "",
    ]
    return " ".join(p for p in parts if p)[:8000]


def _keyword_score(text: str, keywords: list) -> float:
    """
    统计命中的关键词数量，用 sigmoid-like 映射到 [0, 1]。
    """
    if not keywords or not text:
        return 0.0
    hit = sum(1 for kw in keywords if kw in text)
    # 每命中 1 个关键词贡献约 0.15，上限 1.0
    return min(1.0, hit * 0.15)


def _originality_score(text: str, rules: dict) -> float:
    orig_kw = rules.get("originality_keywords", [])
    repost_kw = rules.get("repost_keywords", [])
    if any(kw in text for kw in orig_kw):
        return 1.0
    if any(kw in text for kw in repost_kw):
        return 0.0
    return 0.5


def _expert_and_fact_score(text: str) -> tuple[float, bool, bool]:
    """
    估算专家观点/最新事实分，返回 (score, has_expert, has_fact)。
    """
    has_expert = bool(EXPERT_PATTERN.search(text))
    has_fact = bool(DATA_PATTERN.search(text))

    score = 0.0
    if has_expert:
        score += 0.5
    if has_fact:
        score += 0.5
    return min(1.0, score), has_expert, has_fact
