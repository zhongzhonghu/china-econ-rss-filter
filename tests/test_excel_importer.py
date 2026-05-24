"""测试 excel_importer 模块。"""
import pytest
from pathlib import Path
import tempfile
import shutil
import yaml
import pandas as pd

from src import config_loader
from src.excel_importer import import_sources, _validate_rows, _parse_enabled


@pytest.fixture
def tmp_dirs(monkeypatch, tmp_path):
    """将 config_loader 路径重定向到临时目录。"""
    monkeypatch.setattr(config_loader, "CONFIG_DIR", tmp_path / "config")
    monkeypatch.setattr(config_loader, "OUTPUT_DIR", tmp_path / "output")
    (tmp_path / "config").mkdir()
    (tmp_path / "output").mkdir()
    return tmp_path


def _make_excel(path: Path, rows: list) -> None:
    """创建测试用 Excel 文件。"""
    from src.excel_importer import REQUIRED_COLS
    df = pd.DataFrame(rows)
    for c in REQUIRED_COLS:
        if c not in df.columns:
            df[c] = ""
    df.to_excel(str(path), sheet_name="sources", index=False)


class TestParseEnabled:
    def test_true_values(self):
        for v in ["1", "TRUE", "true", "yes", "Yes", "y"]:
            assert _parse_enabled(v) is True

    def test_false_values(self):
        for v in ["0", "FALSE", "false", "no", "No", ""]:
            assert _parse_enabled(v) is False


class TestImportSourcesNoExcel:
    def test_creates_template_when_no_xlsx(self, tmp_dirs):
        excel_path = tmp_dirs / "config" / "rss_sources.xlsx"
        feeds_yaml = tmp_dirs / "config" / "feeds.yaml"
        report = tmp_dirs / "output" / "rss_sources_validation.md"

        result = import_sources(excel_path, feeds_yaml, report)

        assert result["mode"] == "template_created"
        assert feeds_yaml.exists(), "feeds.yaml should be created"
        assert report.exists(), "validation report should be created"

    def test_sample_feeds_yaml_has_entries(self, tmp_dirs):
        excel_path = tmp_dirs / "config" / "rss_sources.xlsx"
        feeds_yaml = tmp_dirs / "config" / "feeds.yaml"
        report = tmp_dirs / "output" / "rss_sources_validation.md"

        import_sources(excel_path, feeds_yaml, report)

        with open(feeds_yaml, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        assert "feeds" in data
        assert len(data["feeds"]) > 0


class TestImportSourcesWithExcel:
    def test_valid_rows_imported(self, tmp_dirs):
        excel_path = tmp_dirs / "config" / "rss_sources.xlsx"
        feeds_yaml = tmp_dirs / "config" / "feeds.yaml"
        report = tmp_dirs / "output" / "rss_sources_validation.md"

        _make_excel(excel_path, [
            {
                "enabled": 1, "source_id": "s1", "source_name": "测试源",
                "rss_url": "https://example.com/feed1",
                "source_type": "media", "source_quality_score": 0.8,
                "language": "zh", "region_scope": "china",
                "primary_topic_hint": "T01", "notes": "测试",
            }
        ])

        result = import_sources(excel_path, feeds_yaml, report)

        assert result["feed_count"] == 1
        with open(feeds_yaml, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        assert len(data["feeds"]) == 1
        assert data["feeds"][0]["source_id"] == "s1"

    def test_disabled_rows_skipped(self, tmp_dirs):
        excel_path = tmp_dirs / "config" / "rss_sources.xlsx"
        feeds_yaml = tmp_dirs / "config" / "feeds.yaml"
        report = tmp_dirs / "output" / "rss_sources_validation.md"

        _make_excel(excel_path, [
            {
                "enabled": 0, "source_id": "disabled", "source_name": "禁用源",
                "rss_url": "https://example.com/disabled",
                "source_type": "media", "source_quality_score": 0.5,
                "language": "zh", "region_scope": "china",
                "primary_topic_hint": "", "notes": "",
            }
        ])

        result = import_sources(excel_path, feeds_yaml, report)
        assert result["feed_count"] == 0

    def test_duplicate_url_deduplication(self, tmp_dirs):
        excel_path = tmp_dirs / "config" / "rss_sources.xlsx"
        feeds_yaml = tmp_dirs / "config" / "feeds.yaml"
        report = tmp_dirs / "output" / "rss_sources_validation.md"

        same_url = "https://example.com/same"
        _make_excel(excel_path, [
            {
                "enabled": 1, "source_id": "a1", "source_name": "源A",
                "rss_url": same_url, "source_type": "media",
                "source_quality_score": 0.7, "language": "zh",
                "region_scope": "china", "primary_topic_hint": "T01", "notes": "",
            },
            {
                "enabled": 1, "source_id": "a2", "source_name": "源B",
                "rss_url": same_url, "source_type": "media",
                "source_quality_score": 0.7, "language": "zh",
                "region_scope": "china", "primary_topic_hint": "T02", "notes": "",
            },
        ])

        result = import_sources(excel_path, feeds_yaml, report)
        # 重复 URL 只保留第一条
        assert result["feed_count"] == 1

    def test_invalid_primary_topic_skips_field(self, tmp_dirs):
        excel_path = tmp_dirs / "config" / "rss_sources.xlsx"
        feeds_yaml = tmp_dirs / "config" / "feeds.yaml"
        report = tmp_dirs / "output" / "rss_sources_validation.md"

        _make_excel(excel_path, [
            {
                "enabled": 1, "source_id": "s1", "source_name": "源",
                "rss_url": "https://example.com/x",
                "source_type": "media", "source_quality_score": 0.7,
                "language": "zh", "region_scope": "china",
                "primary_topic_hint": "T99",  # 无效
                "notes": "",
            }
        ])

        result = import_sources(excel_path, feeds_yaml, report)
        # 无效 topic 应被跳过，但行本身应被导入（primary_topic_hint 置空）
        assert result["feed_count"] == 1
        with open(feeds_yaml, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        assert data["feeds"][0]["primary_topic_hint"] == ""
