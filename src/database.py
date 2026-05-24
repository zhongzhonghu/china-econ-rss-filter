"""
database.py — SQLite 数据库操作。
所有时间字段统一存储为 UTC ISO 8601 字符串。
"""
import sqlite3
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

CREATE_ARTICLES = """
CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT UNIQUE,
    canonical_url TEXT,
    title TEXT,
    source_id TEXT,
    source TEXT,
    source_type TEXT,
    source_quality_score REAL,
    author TEXT,
    published_at TEXT,
    fetched_at TEXT,
    rss_summary TEXT,
    raw_text TEXT,
    cleaned_text TEXT,
    content_hash TEXT,
    title_hash TEXT,
    extraction_status TEXT,
    rule_keep INTEGER,
    rule_reject_reason TEXT,
    llm_result_json TEXT,
    final_keep INTEGER,
    final_priority_score REAL,
    priority_level TEXT,
    primary_topic TEXT,
    secondary_topics TEXT,
    china_relevance_score REAL,
    economic_relevance_score REAL,
    originality_score REAL,
    expert_or_fact_score REAL,
    noise_score REAL,
    freshness_score REAL,
    has_expert_opinion INTEGER,
    has_latest_economic_fact INTEGER,
    expert_names TEXT,
    institutions TEXT,
    key_facts TEXT,
    expert_viewpoints TEXT,
    llm_summary TEXT,
    reason_for_keep TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_RUNS = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT,
    finished_at TEXT,
    total_fetched INTEGER,
    total_new INTEGER,
    total_rule_candidates INTEGER,
    total_llm_classified INTEGER,
    total_kept INTEGER,
    notes TEXT
);
"""


class Database:
    def __init__(self, db_path: Path = None):
        if db_path is None:
            from . import config_loader
            db_path = config_loader.get_database_path()
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self._create_tables()

    def _create_tables(self):
        self.conn.execute(CREATE_ARTICLES)
        self.conn.execute(CREATE_RUNS)
        self.conn.commit()

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    # ─── Article CRUD ───────────────────────────────────────────────

    def insert_article(self, article: dict) -> Optional[int]:
        """插入文章，URL 重复时忽略。返回新行 id 或 None。"""
        cols = [
            "url", "canonical_url", "title", "source_id", "source",
            "source_type", "source_quality_score", "author", "published_at",
            "fetched_at", "rss_summary", "raw_text", "cleaned_text",
            "content_hash", "title_hash", "extraction_status",
        ]
        data = {c: article.get(c) for c in cols}
        data["fetched_at"] = data.get("fetched_at") or _now_utc()
        placeholders = ", ".join(f":{c}" for c in data)
        col_list = ", ".join(data.keys())
        sql = f"INSERT OR IGNORE INTO articles ({col_list}) VALUES ({placeholders})"
        cur = self.conn.execute(sql, data)
        self.conn.commit()
        # rowcount==0 表示因 UNIQUE 冲突被忽略
        return cur.lastrowid if cur.rowcount > 0 else None

    def update_article(self, article_id: int, **fields):
        """更新文章字段。"""
        fields["updated_at"] = _now_utc()
        set_clause = ", ".join(f"{k} = :{k}" for k in fields)
        fields["_id"] = article_id
        self.conn.execute(f"UPDATE articles SET {set_clause} WHERE id = :_id", fields)
        self.conn.commit()

    def get_article_by_url(self, url: str) -> Optional[dict]:
        row = self.conn.execute("SELECT * FROM articles WHERE url = ?", (url,)).fetchone()
        return dict(row) if row else None

    def get_article_by_content_hash(self, content_hash: str) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM articles WHERE content_hash = ?", (content_hash,)
        ).fetchone()
        return dict(row) if row else None

    def get_recent_articles(self, hours: int = 48) -> list[dict]:
        """返回最近 N 小时内抓取的文章（用于去重比对）。"""
        rows = self.conn.execute(
            "SELECT id, title, source_quality_score FROM articles "
            "WHERE fetched_at >= datetime('now', ?)",
            (f"-{hours} hours",),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_unclassified_articles(self, limit: int = 500) -> list[dict]:
        """返回尚未分类（final_keep IS NULL）且未被规则拒绝的文章。"""
        rows = self.conn.execute(
            "SELECT * FROM articles WHERE final_keep IS NULL "
            "AND (rule_keep = 1 OR rule_keep IS NULL) "
            "ORDER BY published_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_rule_candidates(self) -> list[dict]:
        """返回 rule_keep=1 且尚未做 LLM 分类的文章。"""
        rows = self.conn.execute(
            "SELECT * FROM articles WHERE rule_keep = 1 AND llm_result_json IS NULL "
            "ORDER BY published_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_kept_articles(self, hours: int = 24, limit: int = 200) -> list[dict]:
        """返回 final_keep=1、24h内发布、按优先级排序的文章。

        注意：published_at 存储格式为 "YYYY-MM-DDTHH:MM:SS+00:00"，
        SQLite datetime() 返回 "YYYY-MM-DD HH:MM:SS"（空格分隔）。
        由于 'T'(84) > ' '(32)，直接字符串比较会出错，
        因此使用 strftime 统一两侧为 ISO T 格式再比较。
        """
        rows = self.conn.execute(
            "SELECT * FROM articles "
            "WHERE final_keep = 1 "
            "AND substr(published_at, 1, 19) >= strftime('%Y-%m-%dT%H:%M:%S', datetime('now', ?)) "
            "ORDER BY final_priority_score DESC "
            "LIMIT ?",
            (f"-{hours} hours", limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_all_kept_articles(self) -> list[dict]:
        """返回所有 final_keep=1 的文章（用于摘要生成）。"""
        rows = self.conn.execute(
            "SELECT * FROM articles WHERE final_keep = 1 "
            "ORDER BY final_priority_score DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_stats(self) -> dict:
        total = self.conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        kept = self.conn.execute(
            "SELECT COUNT(*) FROM articles WHERE final_keep = 1"
        ).fetchone()[0]
        rule_kept = self.conn.execute(
            "SELECT COUNT(*) FROM articles WHERE rule_keep = 1"
        ).fetchone()[0]
        llm_done = self.conn.execute(
            "SELECT COUNT(*) FROM articles WHERE llm_result_json IS NOT NULL"
        ).fetchone()[0]
        return {
            "total": total,
            "rule_kept": rule_kept,
            "llm_classified": llm_done,
            "final_kept": kept,
        }

    # ─── Run CRUD ────────────────────────────────────────────────────

    def insert_run(self, run: dict) -> int:
        run.setdefault("started_at", _now_utc())
        cur = self.conn.execute(
            "INSERT INTO runs (started_at, notes) VALUES (:started_at, :notes)",
            {"started_at": run["started_at"], "notes": run.get("notes", "")},
        )
        self.conn.commit()
        return cur.lastrowid

    def update_run(self, run_id: int, **fields):
        set_clause = ", ".join(f"{k} = :{k}" for k in fields)
        fields["_id"] = run_id
        self.conn.execute(f"UPDATE runs SET {set_clause} WHERE id = :_id", fields)
        self.conn.commit()


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
