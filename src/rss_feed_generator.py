"""
rss_feed_generator.py — 生成 RSS 2.0 XML（output/selected_feed.xml）。
仅含 24h 内发布的文章，最多 200 条，CDATA 描述。
"""
import json
import logging
import xml.sax.saxutils as saxutils
from datetime import datetime, timezone
from email.utils import format_datetime

from . import config_loader
from .database import Database

logger = logging.getLogger(__name__)


def generate_feed(db: Database, limit: int = 200, hours: int = 24) -> dict:
    """
    生成 output/selected_feed.xml。
    """
    topics = config_loader.load_topics()
    articles = db.get_kept_articles(hours=hours, limit=limit)

    output_path = config_loader.OUTPUT_DIR / "selected_feed.xml"
    config_loader.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    base_url = config_loader.get_public_feed_base_url()
    xml_str = _build_feed_xml(articles, topics, base_url)
    output_path.write_text(xml_str, encoding="utf-8")

    logger.info(f"Feed generated: {len(articles)} articles → {output_path}")
    return {"article_count": len(articles), "path": str(output_path)}


def _build_feed_xml(articles: list, topics: dict, base_url: str) -> str:
    now_rfc = _to_rfc822(datetime.now(timezone.utc))
    feed_link = (base_url.rstrip("/") + "/selected_feed.xml") if base_url else "selected_feed.xml"

    items = "\n".join(_build_item(a, topics) for a in articles)

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">\n'
        "<channel>\n"
        "  <title>中国经济精选 RSS</title>\n"
        f"  <link>{saxutils.escape(feed_link)}</link>\n"
        "  <description>AI 精选中国经济、金融、产业新闻与深度分析（24小时内，最多200条）</description>\n"
        "  <language>zh-cn</language>\n"
        f"  <lastBuildDate>{now_rfc}</lastBuildDate>\n"
        f'  <atom:link href="{saxutils.escape(feed_link)}" rel="self" type="application/rss+xml"/>\n'
        f"{items}\n"
        "</channel>\n"
        "</rss>"
    )


def _build_item(article: dict, topics: dict) -> str:
    title = saxutils.escape(article.get("title") or "（无标题）")
    url = saxutils.escape(article.get("url") or "")
    guid = article.get("content_hash") or str(article.get("id", ""))
    pub_date = _to_rfc822_str(article.get("published_at", ""))
    source = saxutils.escape(article.get("source") or "")

    primary = article.get("primary_topic") or ""
    topic_label = topics.get(primary, primary)
    category = saxutils.escape(f"{primary} {topic_label}") if primary else ""

    description_html = _build_description(article, topics)
    # CDATA 内部不允许 "]]>"，转义之
    description_html = description_html.replace("]]>", "]]]]><![CDATA[>")

    lines = [
        "  <item>",
        f"    <title>{title}</title>",
        f"    <link>{url}</link>",
        f'    <guid isPermaLink="false">{saxutils.escape(guid)}</guid>',
        f"    <pubDate>{pub_date}</pubDate>",
        f"    <source>{source}</source>",
    ]
    if category:
        lines.append(f"    <category>{category}</category>")

    # 副主题
    secondary = _load_json_list(article.get("secondary_topics"))
    for st in secondary:
        st_label = topics.get(st, st)
        lines.append(f"    <category>{saxutils.escape(f'{st} {st_label}')}</category>")

    lines.append(f"    <description><![CDATA[{description_html}]]></description>")
    lines.append("  </item>")
    return "\n".join(lines)


def _build_description(article: dict, topics: dict) -> str:
    source = article.get("source") or ""
    summary = article.get("rss_summary") or article.get("llm_summary") or ""
    url = article.get("url") or ""

    parts = []
    if source:
        parts.append(f"<p><strong>{_h(source)}</strong></p>")
    if summary:
        parts.append(f"<p>{_h(summary)}</p>")
    if url:
        parts.append(f'<p><a href="{_h(url)}">阅读原文</a></p>')
    return "".join(parts)


def _h(text: str) -> str:
    """HTML 转义普通文本。"""
    return saxutils.escape(str(text or ""))


def _to_rfc822(dt: datetime) -> str:
    """datetime 对象 → RFC 822 字符串。"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return format_datetime(dt)


def _to_rfc822_str(s: str) -> str:
    """ISO 字符串 → RFC 822 字符串。"""
    if not s:
        return _to_rfc822(datetime.now(timezone.utc))
    try:
        from .scoring import _parse_dt
        dt = _parse_dt(s)
        return _to_rfc822(dt)
    except Exception:
        return _to_rfc822(datetime.now(timezone.utc))


def _load_json_list(val) -> list:
    if not val:
        return []
    if isinstance(val, list):
        return val
    try:
        result = json.loads(val)
        return result if isinstance(result, list) else []
    except Exception:
        return []
