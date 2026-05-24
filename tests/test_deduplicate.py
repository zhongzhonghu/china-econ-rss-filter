"""测试 deduplicate 模块。"""
import pytest
from pathlib import Path
import tempfile

from src.database import Database
from src.deduplicate import run_deduplication, _dedup_by_content_hash, _dedup_by_fuzzy_title


@pytest.fixture
def db(tmp_path):
    """每个测试使用独立的临时数据库。"""
    db_path = tmp_path / "test.sqlite"
    d = Database(db_path)
    yield d
    d.close()


def _insert(db: Database, url: str, title: str, content_hash: str = None,
            source_quality_score: float = 0.7) -> int:
    """插入测试文章，返回 id。"""
    rid = db.insert_article({
        "url": url,
        "title": title,
        "content_hash": content_hash or url[:32],
        "source_quality_score": source_quality_score,
        "published_at": "2026-05-24T10:00:00+00:00",
        "fetched_at": "2026-05-24T10:00:00+00:00",
    })
    return rid


class TestUrlDedup:
    def test_same_url_not_inserted_twice(self, db):
        id1 = _insert(db, "https://example.com/article", "标题A", "hash1")
        id2 = _insert(db, "https://example.com/article", "标题B", "hash2")
        # 第二次 insert 因 UNIQUE 约束返回 None
        assert id1 is not None
        assert id2 is None


class TestContentHashDedup:
    def test_same_hash_deduped(self, db):
        id1 = _insert(db, "https://example.com/a1", "标题A", "samehash123")
        id2 = _insert(db, "https://example.com/a2", "标题A副本", "samehash123")

        _dedup_by_content_hash(db)

        row1 = db.conn.execute("SELECT final_keep FROM articles WHERE id=?", (id1,)).fetchone()
        row2 = db.conn.execute("SELECT final_keep FROM articles WHERE id=?", (id2,)).fetchone()

        # 至少有一篇被标记为不保留（id 小的保留）
        assert row2["final_keep"] == 0

    def test_different_hash_not_deduped(self, db):
        _insert(db, "https://example.com/b1", "标题1", "hash_aaa")
        _insert(db, "https://example.com/b2", "标题2", "hash_bbb")

        removed = _dedup_by_content_hash(db)
        assert removed == 0


class TestFuzzyTitleDedup:
    def test_very_similar_titles_deduped(self, db):
        id1 = _insert(db, "https://x.com/c1", "中国GDP第一季度增速超预期达到5.3%", "h1", source_quality_score=0.8)
        id2 = _insert(db, "https://x.com/c2", "中国GDP第一季度增速超预期达到5.3%！", "h2", source_quality_score=0.6)

        removed = _dedup_by_fuzzy_title(db, hours=48)
        assert removed >= 1

        # 质量更高（score=0.8）的应被保留
        row1 = db.conn.execute("SELECT final_keep FROM articles WHERE id=?", (id1,)).fetchone()
        assert row1["final_keep"] != 0  # id1 应保留（或未被标记）

    def test_different_titles_not_deduped(self, db):
        _insert(db, "https://x.com/d1", "中国GDP增速", "h3")
        _insert(db, "https://x.com/d2", "美联储加息对汇率的影响", "h4")

        removed = _dedup_by_fuzzy_title(db, hours=48)
        assert removed == 0


class TestRunDeduplication:
    def test_full_deduplication(self, db):
        _insert(db, "https://x.com/e1", "完全相同的标题", "same_hash")
        _insert(db, "https://x.com/e2", "完全相同的标题副本", "same_hash")

        removed = run_deduplication(db)
        assert removed >= 1
