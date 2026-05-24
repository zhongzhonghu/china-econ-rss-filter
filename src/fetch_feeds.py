"""
fetch_feeds.py — 并行抓取 RSS feeds，存入数据库。
正文提取推迟到规则过滤后执行（只对保留文章提取，约 10-15%）。

超时策略：
- requests 取 feed XML：12s
- socket 全局兜底：20s
- 并行 feed 数：min(feeds, 5)
"""
import calendar
import hashlib
import logging
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeout
from datetime import datetime, timezone
from time import struct_time
from typing import Optional

import feedparser
import requests
from bs4 import BeautifulSoup

from . import config_loader
from .database import Database

logger = logging.getLogger(__name__)

FEED_TIMEOUT = 12      # 取 RSS XML 的超时（秒）
MAX_FEED_WORKERS = 5   # 并行 feed 数
FEED_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; RSSBot/1.0)",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}


def fetch_all(db: Database, max_articles: int = None) -> dict:
    """
    并行读取所有 enabled feed，写入数据库。
    不在此阶段提取文章正文（由 rule_filter 后的步骤处理）。
    """
    socket.setdefaulttimeout(20)  # 全局兜底，防止 feedparser 无限挂起

    if max_articles is None:
        max_articles = config_loader.get_max_articles()

    feeds = [f for f in config_loader.load_feeds() if f.get("enabled", True) and f.get("url")]
    if not feeds:
        logger.warning("No feeds configured. Run import-sources first.")
        return {"total_fetched": 0, "total_new": 0, "errors": []}

    # ── 第一阶段：并行抓取所有 feed XML ──────────────────────────────────
    fetched_feeds: list[tuple[dict, list]] = []  # [(feed_conf, entries), ...]
    errors: list[str] = []

    with ThreadPoolExecutor(max_workers=min(len(feeds), MAX_FEED_WORKERS)) as pool:
        futures = {pool.submit(_fetch_feed_entries, fc): fc for fc in feeds}
        for future in as_completed(futures, timeout=60):
            fc = futures[future]
            name = fc.get("name", fc.get("url", ""))
            try:
                entries = future.result(timeout=2)  # result 已就绪，2s 只是保险
                fetched_feeds.append((fc, entries))
                logger.info(f"Fetched feed '{name}': {len(entries)} entries")
            except FuturesTimeout:
                msg = f"Feed '{name}' timed out"
                logger.error(msg)
                errors.append(msg)
            except Exception as e:
                msg = f"Feed '{name}' failed: {e}"
                logger.error(msg)
                errors.append(msg)

    # ── 第二阶段：去重并写库（主线程，串行） ─────────────────────────────
    total_fetched = 0
    total_new = 0

    for feed_conf, entries in fetched_feeds:
        remaining = max_articles - total_fetched
        if remaining <= 0:
            break
        fetched, new_count = _insert_entries(db, feed_conf, entries[:remaining])
        total_fetched += fetched
        total_new += new_count

    logger.info(f"fetch_all done: total_fetched={total_fetched}, total_new={total_new}, errors={len(errors)}")
    return {"total_fetched": total_fetched, "total_new": total_new, "errors": errors}


# ─── Feed 抓取（在线程中执行） ────────────────────────────────────────────

def _fetch_feed_entries(feed_conf: dict) -> list[dict]:
    """
    用 requests 取 RSS XML（有 timeout），再用 feedparser 解析。
    返回 entry 字典列表。
    """
    url = feed_conf["url"]
    try:
        resp = requests.get(url, timeout=FEED_TIMEOUT, headers=FEED_HEADERS, verify=False)
        resp.raise_for_status()
        content = resp.content  # bytes
        content_type = resp.headers.get("content-type", "")
    except requests.Timeout:
        raise TimeoutError(f"Feed URL timed out after {FEED_TIMEOUT}s: {url}")
    except Exception as e:
        raise RuntimeError(f"HTTP error fetching feed: {e}")

    parsed = feedparser.parse(content, response_headers={"content-type": content_type})
    return parsed.entries


# ─── 写库（主线程） ──────────────────────────────────────────────────────

def _insert_entries(db: Database, feed_conf: dict, entries) -> tuple[int, int]:
    fetched = 0
    new_count = 0

    for entry in entries:
        article_url = _get_entry_url(entry)
        if not article_url:
            continue

        if db.get_article_by_url(article_url):
            fetched += 1
            continue

        title = _clean(getattr(entry, "title", ""))
        summary = _clean(getattr(entry, "summary", "") or getattr(entry, "description", ""))
        author = _clean(getattr(entry, "author", ""))
        published_at = _parse_published(entry)

        content_hash = _sha256(title + article_url)
        title_hash = _sha256(title)

        article = {
            "url": article_url,
            "title": title,
            "source_id": feed_conf.get("source_id", ""),
            "source": feed_conf.get("name", ""),
            "source_type": feed_conf.get("source_type", "unknown"),
            "source_quality_score": feed_conf.get("source_quality_score", 0.5),
            "author": author,
            "published_at": published_at,
            "rss_summary": summary[:2000] if summary else "",
            "content_hash": content_hash,
            "title_hash": title_hash,
            "extraction_status": "pending",  # 正文提取延迟到规则过滤后
        }

        row_id = db.insert_article(article)
        fetched += 1
        if row_id:
            new_count += 1

    return fetched, new_count


# ─── 工具函数 ─────────────────────────────────────────────────────────────

def _get_entry_url(entry) -> Optional[str]:
    link = getattr(entry, "link", "") or ""
    if link:
        return link.strip()
    eid = getattr(entry, "id", "") or ""
    if eid.startswith("http"):
        return eid.strip()
    return None


def _parse_published(entry) -> str:
    tp = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if tp and isinstance(tp, struct_time):
        try:
            ts = calendar.timegm(tp)
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            return dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")
        except Exception:
            pass
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _clean(text: str) -> str:
    if not text:
        return ""
    try:
        return BeautifulSoup(text, "html.parser").get_text(separator=" ", strip=True)
    except Exception:
        return str(text).strip()


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:32]
