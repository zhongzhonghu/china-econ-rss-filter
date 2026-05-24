"""
excel_importer.py — 从 Excel 读取 RSS 源配置，验证，生成 feeds.yaml。
若 rss_sources.xlsx 不存在，自动生成模板。
"""
import re
import logging
from pathlib import Path
from datetime import datetime

import pandas as pd
import yaml

from . import config_loader

logger = logging.getLogger(__name__)

REQUIRED_COLS = [
    "enabled", "source_id", "source_name", "rss_url",
    "source_type", "source_quality_score", "language",
    "region_scope", "primary_topic_hint", "notes",
]

OPTIONAL_COLS = [
    "wechat_account", "rss_provider", "original_homepage",
    "update_frequency", "paywall_status", "requires_fulltext",
    "include_keywords", "exclude_keywords", "topic_hints",
    "priority_group", "owner_notes",
]

VALID_SOURCE_TYPES = {
    "official", "media", "think_tank", "sell_side",
    "wechat", "academic", "industry", "unknown",
}

TOPIC_PATTERN = re.compile(r"^T(0[1-9]|1[0-9]|2[0-2])$")


def import_sources(
    excel_path: Path = None,
    feeds_yaml_path: Path = None,
    validation_report_path: Path = None,
) -> dict:
    """
    主入口。读取 xlsx → 验证 → 生成 feeds.yaml + 验证报告。
    若 xlsx 不存在，生成模板并返回示例 feeds.yaml。
    """
    if excel_path is None:
        excel_path = config_loader.CONFIG_DIR / "rss_sources.xlsx"
    if feeds_yaml_path is None:
        feeds_yaml_path = config_loader.CONFIG_DIR / "feeds.yaml"
    if validation_report_path is None:
        validation_report_path = config_loader.OUTPUT_DIR / "rss_sources_validation.md"

    config_loader.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if not excel_path.exists():
        logger.info(f"rss_sources.xlsx not found. Creating template...")
        _create_template(excel_path)
        _write_sample_feeds_yaml(feeds_yaml_path)
        _write_validation_report(
            validation_report_path,
            warnings=["rss_sources.xlsx 不存在，已创建模板文件。请填写后重新运行。"],
            valid_rows=[],
            skipped_rows=[],
        )
        return {"mode": "template_created", "feed_count": 0}

    df = _read_excel(excel_path)
    if df is None:
        _write_validation_report(
            validation_report_path,
            warnings=["无法读取 Excel 文件，请检查格式。"],
            valid_rows=[],
            skipped_rows=[],
        )
        return {"mode": "error", "feed_count": 0}

    valid_rows, skipped_rows, warnings = _validate_rows(df)
    _write_feeds_yaml(feeds_yaml_path, valid_rows)
    _write_validation_report(validation_report_path, warnings, valid_rows, skipped_rows)

    logger.info(f"import-sources: {len(valid_rows)} valid feeds, {len(skipped_rows)} skipped")
    return {"mode": "imported", "feed_count": len(valid_rows)}


# ─── Internal helpers ────────────────────────────────────────────────────────

def _read_excel(path: Path):
    try:
        df = pd.read_excel(path, sheet_name="sources", dtype=str)
        df.columns = [c.strip().lower() for c in df.columns]
        df = df.fillna("")
        return df
    except Exception as e:
        logger.error(f"Failed to read Excel: {e}")
        return None


def _parse_enabled(val: str) -> bool:
    return str(val).strip().lower() in {"1", "true", "yes", "y", "是"}


def _validate_rows(df: pd.DataFrame):
    warnings = []
    valid_rows = []
    skipped_rows = []
    seen_urls = {}
    seen_ids = {}

    # 检查必须列
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        warnings.append(f"缺少必要列：{missing}")
        return valid_rows, skipped_rows, warnings

    for idx, row in df.iterrows():
        row_num = idx + 2  # Excel 行号（1-based + header）

        if not _parse_enabled(row.get("enabled", "0")):
            skipped_rows.append({"row": row_num, "reason": "disabled"})
            continue

        errors = []

        source_id = str(row.get("source_id", "")).strip()
        source_name = str(row.get("source_name", "")).strip()
        rss_url = str(row.get("rss_url", "")).strip()

        if not source_name:
            errors.append("source_name 为空")
        if not rss_url:
            errors.append("rss_url 为空")

        # source_quality_score
        try:
            score = float(row.get("source_quality_score", "0.5") or "0.5")
            score = max(0.0, min(1.0, score))
        except ValueError:
            score = 0.5
            warnings.append(f"行 {row_num}: source_quality_score 无效，使用默认值 0.5")

        # primary_topic_hint
        topic_hint = str(row.get("primary_topic_hint", "")).strip()
        if topic_hint and not TOPIC_PATTERN.match(topic_hint):
            warnings.append(f"行 {row_num}: primary_topic_hint '{topic_hint}' 无效（须为 T01-T22），已清空")
            topic_hint = ""

        # topic_hints（多个，分号分隔）
        topic_hints_str = str(row.get("topic_hints", "")).strip()
        topic_hints = []
        if topic_hints_str:
            for t in re.split(r"[;,]", topic_hints_str):
                t = t.strip()
                if TOPIC_PATTERN.match(t):
                    topic_hints.append(t)
                else:
                    warnings.append(f"行 {row_num}: topic_hints 中 '{t}' 无效，已跳过")

        if errors:
            skipped_rows.append({"row": row_num, "source": source_name, "errors": errors})
            for e in errors:
                warnings.append(f"行 {row_num}: {e}（已跳过）")
            continue

        # URL 去重
        if rss_url in seen_urls:
            warnings.append(
                f"行 {row_num}: rss_url '{rss_url}' 与行 {seen_urls[rss_url]} 重复，已跳过"
            )
            skipped_rows.append({"row": row_num, "source": source_name, "errors": ["duplicate url"]})
            continue
        seen_urls[rss_url] = row_num

        # source_id 重复警告
        if source_id and source_id in seen_ids:
            warnings.append(f"行 {row_num}: source_id '{source_id}' 与行 {seen_ids[source_id]} 重复")
        if source_id:
            seen_ids[source_id] = row_num

        feed = {
            "source_id": source_id or f"feed_{row_num:03d}",
            "name": source_name,
            "url": rss_url,
            "source_type": str(row.get("source_type", "unknown")).strip() or "unknown",
            "source_quality_score": round(score, 4),
            "language": str(row.get("language", "zh")).strip() or "zh",
            "region_scope": str(row.get("region_scope", "china")).strip() or "china",
            "primary_topic_hint": topic_hint,
            "topic_hints": topic_hints,
            "enabled": True,
            "notes": str(row.get("notes", "")).strip(),
        }

        # 可选列
        for col in OPTIONAL_COLS:
            val = str(row.get(col, "")).strip()
            if val:
                feed[col] = val

        valid_rows.append(feed)

    return valid_rows, skipped_rows, warnings


def _write_feeds_yaml(path: Path, feeds: list):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"feeds": feeds}
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    logger.info(f"Written: {path}")


def _write_validation_report(path: Path, warnings: list, valid_rows: list, skipped_rows: list):
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# RSS 源验证报告",
        f"\n生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"\n## 概要",
        f"- 有效源数量：{len(valid_rows)}",
        f"- 跳过行数：{len(skipped_rows)}",
        f"- 警告数量：{len(warnings)}",
    ]
    if warnings:
        lines.append("\n## 警告与错误")
        for w in warnings:
            lines.append(f"- {w}")
    if skipped_rows:
        lines.append("\n## 跳过的行")
        for s in skipped_rows:
            reason = s.get("reason") or ", ".join(s.get("errors", []))
            name = s.get("source", "")
            lines.append(f"- 行 {s['row']} {name}: {reason}")
    if valid_rows:
        lines.append("\n## 有效源列表")
        for f in valid_rows:
            lines.append(f"- `{f['source_id']}` {f['name']} ({f['url']})")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    logger.info(f"Written: {path}")


def _create_template(excel_path: Path):
    """生成含示例行的 xlsx 模板。"""
    excel_path.parent.mkdir(parents=True, exist_ok=True)
    template_path = config_loader.CONFIG_DIR / "rss_sources_template.xlsx"

    sample_rows = [
        {
            "enabled": 1,
            "source_id": "cf40",
            "source_name": "中国金融四十人论坛",
            "rss_url": "https://rsshub.app/cf40/articles",
            "source_type": "think_tank",
            "source_quality_score": 0.85,
            "language": "zh",
            "region_scope": "china",
            "primary_topic_hint": "T03",
            "notes": "宏观政策与金融市场",
            "rss_provider": "rsshub",
            "topic_hints": "T03;T17",
            "priority_group": "core",
        },
        {
            "enabled": 1,
            "source_id": "caixin",
            "source_name": "财新网",
            "rss_url": "https://rsshub.app/caixin/finance/regulation",
            "source_type": "media",
            "source_quality_score": 0.90,
            "language": "zh",
            "region_scope": "china",
            "primary_topic_hint": "T01",
            "notes": "财经深度报道",
            "rss_provider": "rsshub",
            "priority_group": "core",
        },
        {
            "enabled": 0,
            "source_id": "example_disabled",
            "source_name": "示例禁用源",
            "rss_url": "https://example.com/feed",
            "source_type": "unknown",
            "source_quality_score": 0.50,
            "language": "zh",
            "region_scope": "china",
            "primary_topic_hint": "",
            "notes": "此行已禁用，仅供示例",
        },
    ]

    all_cols = REQUIRED_COLS + [c for c in OPTIONAL_COLS if c not in REQUIRED_COLS]
    df = pd.DataFrame(sample_rows)
    for c in all_cols:
        if c not in df.columns:
            df[c] = ""
    df = df[all_cols]

    for p in [template_path, excel_path.parent / "rss_sources_template.xlsx"]:
        df.to_excel(str(p), sheet_name="sources", index=False)
    logger.info(f"Created template: {template_path}")


def _write_sample_feeds_yaml(path: Path):
    """写入两个示例 feed，使管道能空转。"""
    sample = {
        "feeds": [
            {
                "source_id": "cf40",
                "name": "中国金融四十人论坛（示例）",
                "url": "https://rsshub.app/cf40/articles",
                "source_type": "think_tank",
                "source_quality_score": 0.85,
                "language": "zh",
                "region_scope": "china",
                "primary_topic_hint": "T03",
                "topic_hints": ["T03", "T17"],
                "enabled": True,
                "notes": "示例条目，请在 rss_sources.xlsx 中填写真实源",
            },
            {
                "source_id": "caixin",
                "name": "财新网（示例）",
                "url": "https://rsshub.app/caixin/finance/regulation",
                "source_type": "media",
                "source_quality_score": 0.90,
                "language": "zh",
                "region_scope": "china",
                "primary_topic_hint": "T01",
                "topic_hints": ["T01"],
                "enabled": True,
                "notes": "示例条目",
            },
        ]
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(sample, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    logger.info(f"Written sample feeds.yaml: {path}")
