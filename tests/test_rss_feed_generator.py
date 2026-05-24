"""测试 rss_feed_generator 模块。"""
import pytest
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timezone, timedelta

from src.database import Database
from src.rss_feed_generator import generate_feed, _build_feed_xml, _to_rfc822


@pytest.fixture
def db(tmp_path, monkeypatch):
    from src import config_loader
    monkeypatch.setattr(config_loader, "OUTPUT_DIR", tmp_path / "output")
    (tmp_path / "output").mkdir()
    d = Database(tmp_path / "test.sqlite")
    yield d
    d.close()


def _insert_kept_article(db: Database, title: str, url: str,
                          published_at: str = None, score: float = 0.8) -> int:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    if published_at is None:
        published_at = now
    rid = db.insert_article({
        "url": url,
        "title": title,
        "content_hash": url[-16:],
        "source": "测试源",
        "published_at": published_at,
        "fetched_at": now,
        "rss_summary": "文章摘要",
    })
    if rid:
        db.update_article(
            rid,
            final_keep=1,
            final_priority_score=score,
            priority_level="High",
            primary_topic="T01",
            secondary_topics='["T03"]',
            rule_keep=1,
            llm_summary="LLM摘要",
            reason_for_keep="包含权威数据",
            key_facts='["GDP增长5.3%"]',
            expert_viewpoints='[]',
        )
    return rid


class TestToRfc822:
    def test_utc_datetime(self):
        dt = datetime(2026, 5, 24, 9, 15, 0, tzinfo=timezone.utc)
        result = _to_rfc822(dt)
        assert "2026" in result
        assert "May" in result


class TestBuildFeedXml:
    def test_valid_rss_structure(self):
        topics = {"T01": "宏观增长、GDP、周期、PMI"}
        xml_str = _build_feed_xml([], topics, "")
        root = ET.fromstring(xml_str)
        assert root.tag == "rss"
        assert root.attrib.get("version") == "2.0"
        channel = root.find("channel")
        assert channel is not None

    def test_item_contains_cdata(self):
        articles = [{
            "id": 1, "title": "测试标题", "url": "https://example.com/test",
            "content_hash": "abc123", "published_at": "2026-05-24T10:00:00+00:00",
            "source": "测试源", "primary_topic": "T01",
            "secondary_topics": '["T03"]',
            "final_priority_score": 0.85, "priority_level": "High",
            "key_facts": '["事实一"]', "expert_viewpoints": '[]',
            "llm_summary": "测试摘要", "reason_for_keep": "高质量",
            "rss_summary": "RSS摘要",
        }]
        topics = {"T01": "宏观增长", "T03": "货币政策"}
        xml_str = _build_feed_xml(articles, topics, "")
        assert "<![CDATA[" in xml_str

    def test_special_chars_escaped(self):
        articles = [{
            "id": 1, "title": "标题 & <测试>", "url": "https://example.com/x",
            "content_hash": "xyz", "published_at": "2026-05-24T10:00:00+00:00",
            "source": "源 & 测试", "primary_topic": "T01",
            "secondary_topics": "[]",
            "final_priority_score": 0.7, "priority_level": "Medium",
            "key_facts": "[]", "expert_viewpoints": "[]",
            "llm_summary": "", "reason_for_keep": "",
            "rss_summary": "",
        }]
        topics = {"T01": "宏观增长"}
        xml_str = _build_feed_xml(articles, topics, "")
        # 特殊字符应被转义，XML 应可解析
        root = ET.fromstring(xml_str)
        assert root is not None


class TestGenerateFeed:
    def test_generates_valid_xml_file(self, db, tmp_path, monkeypatch):
        from src import config_loader
        monkeypatch.setattr(config_loader, "OUTPUT_DIR", tmp_path / "output")
        (tmp_path / "output").mkdir(exist_ok=True)

        _insert_kept_article(db, "测试文章", "https://example.com/art1")

        result = generate_feed(db, limit=200, hours=24)
        feed_path = tmp_path / "output" / "selected_feed.xml"
        assert feed_path.exists()

        # 验证 XML 可解析
        root = ET.parse(str(feed_path)).getroot()
        assert root.tag == "rss"

    def test_24h_filter(self, db, tmp_path, monkeypatch):
        from src import config_loader
        monkeypatch.setattr(config_loader, "OUTPUT_DIR", tmp_path / "output")
        (tmp_path / "output").mkdir(exist_ok=True)

        # 25h 前发布 → 不应出现在 feed 中
        old_time = (datetime.now(timezone.utc) - timedelta(hours=25)).strftime("%Y-%m-%dT%H:%M:%S+00:00")
        _insert_kept_article(db, "旧文章", "https://example.com/old", published_at=old_time)

        # 1h 前发布 → 应出现在 feed 中
        new_time = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S+00:00")
        _insert_kept_article(db, "新文章", "https://example.com/new", published_at=new_time)

        result = generate_feed(db, limit=200, hours=24)
        # 只有新文章应该在 feed 中
        assert result["article_count"] == 1

    def test_max_200_limit(self, db, tmp_path, monkeypatch):
        from src import config_loader
        monkeypatch.setattr(config_loader, "OUTPUT_DIR", tmp_path / "output")
        (tmp_path / "output").mkdir(exist_ok=True)

        # 插入 5 篇文章，限制 3 条
        for i in range(5):
            _insert_kept_article(db, f"文章{i}", f"https://example.com/a{i}")

        result = generate_feed(db, limit=3, hours=24)
        assert result["article_count"] <= 3
