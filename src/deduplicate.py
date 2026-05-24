"""
deduplicate.py — 三层去重：URL（DB约束）、content_hash、rapidfuzz 标题模糊匹配。
"""
import logging

from rapidfuzz import fuzz

from .database import Database

logger = logging.getLogger(__name__)

FUZZY_THRESHOLD = 92.0  # rapidfuzz 返回 0-100


def run_deduplication(db: Database, hours: int = 48) -> int:
    """
    对最近 N 小时内的文章执行去重（URL 去重已由 DB UNIQUE 约束完成）。
    返回被去重的文章总数。
    """
    removed = 0

    # 1. content_hash 去重（保留最早一条）
    removed += _dedup_by_content_hash(db)

    # 2. 标题模糊去重
    removed += _dedup_by_fuzzy_title(db, hours=hours)

    if removed:
        logger.info(f"Deduplication removed {removed} articles")
    return removed


def _dedup_by_content_hash(db: Database) -> int:
    """相同 content_hash 保留最早（id 最小）的一条，其余标记拒绝。"""
    rows = db.conn.execute(
        """
        SELECT content_hash, MIN(id) as keep_id, COUNT(*) as cnt
        FROM articles
        WHERE content_hash IS NOT NULL AND content_hash != ''
          AND final_keep IS NULL
        GROUP BY content_hash
        HAVING cnt > 1
        """
    ).fetchall()

    removed = 0
    for row in rows:
        dup_ids = db.conn.execute(
            "SELECT id FROM articles WHERE content_hash = ? AND id != ? AND final_keep IS NULL",
            (row["content_hash"], row["keep_id"]),
        ).fetchall()
        for dup in dup_ids:
            db.update_article(
                dup["id"],
                final_keep=0,
                rule_keep=0,
                rule_reject_reason="duplicate_content_hash",
            )
            removed += 1
    return removed


def _dedup_by_fuzzy_title(db: Database, hours: int = 48) -> int:
    """在最近 N 小时内使用 rapidfuzz 做标题模糊去重。"""
    articles = db.get_recent_articles(hours=hours)
    # 只对未被拒绝的文章做比较
    candidates = [
        a for a in articles
        if a.get("title") and len(a["title"]) > 5
    ]

    # 过滤掉已标记拒绝的
    active_ids = set(
        row[0] for row in db.conn.execute(
            "SELECT id FROM articles WHERE final_keep IS NULL OR final_keep = 1"
        ).fetchall()
    )
    candidates = [a for a in candidates if a["id"] in active_ids]

    removed_ids = set()
    removed = 0

    for i in range(len(candidates)):
        if candidates[i]["id"] in removed_ids:
            continue
        title_i = candidates[i]["title"]
        score_i = candidates[i].get("source_quality_score") or 0.5

        for j in range(i + 1, len(candidates)):
            if candidates[j]["id"] in removed_ids:
                continue
            title_j = candidates[j]["title"]
            ratio = fuzz.ratio(title_i, title_j)
            if ratio >= FUZZY_THRESHOLD:
                score_j = candidates[j].get("source_quality_score") or 0.5
                # 保留 source_quality_score 更高的
                if score_i >= score_j:
                    loser_id = candidates[j]["id"]
                else:
                    loser_id = candidates[i]["id"]

                if loser_id not in removed_ids:
                    db.update_article(
                        loser_id,
                        final_keep=0,
                        rule_keep=0,
                        rule_reject_reason="duplicate_title_fuzzy",
                    )
                    removed_ids.add(loser_id)
                    removed += 1

                if loser_id == candidates[i]["id"]:
                    break  # i 已被移除，跳出内循环

    return removed
