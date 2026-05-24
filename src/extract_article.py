"""
extract_article.py — 文章正文提取。
trafilatura 优先，readability-lxml + BeautifulSoup 兜底。

超时策略：每篇 6s HTTP，并行最多 4 线程。
"""
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeout

import requests
from bs4 import BeautifulSoup

from .database import Database

logger = logging.getLogger(__name__)

TIMEOUT = 6          # 每篇 HTTP 超时（秒），比 fetch 更激进
MAX_WORKERS = 4      # 并行提取线程数
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def extract_batch(db: Database) -> dict:
    """
    对所有 rule_keep=1 且 extraction_status='pending' 的文章并行提取正文。
    提取后更新数据库。返回统计信息。
    """
    rows = db.conn.execute(
        "SELECT id, url FROM articles WHERE rule_keep = 1 AND extraction_status = 'pending'"
    ).fetchall()

    if not rows:
        return {"attempted": 0, "ok": 0, "fallback": 0, "failed": 0}

    stats = {"attempted": len(rows), "ok": 0, "fallback": 0, "failed": 0}

    def _process(row):
        result = extract(row["url"])
        return row["id"], result

    # 整体超时：按 worker 并行推算，每批 TIMEOUT 秒，加 60s 缓冲
    overall_timeout = (len(rows) // MAX_WORKERS + 1) * TIMEOUT + 60

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(_process, row): row for row in rows}
        try:
            for future in as_completed(futures, timeout=overall_timeout):
                try:
                    article_id, result = future.result(timeout=2)
                    db.update_article(
                        article_id,
                        cleaned_text=result["cleaned_text"],
                        extraction_status=result["extraction_status"],
                    )
                    stats[result["extraction_status"]] = stats.get(result["extraction_status"], 0) + 1
                except Exception as e:
                    row = futures[future]
                    logger.warning(f"Extraction failed for id={row['id']}: {e}")
                    stats["failed"] += 1
        except FuturesTimeout:
            logger.warning("extract_batch: overall timeout exceeded, remaining articles skipped")

    logger.info(
        f"extract_batch: {stats['attempted']} attempted, "
        f"{stats.get('ok', 0)} ok, {stats.get('fallback', 0)} fallback, "
        f"{stats.get('failed', 0)} failed"
    )
    return stats


def extract(url: str, html: str = None) -> dict:
    """
    提取文章正文。
    - html 参数可选，若已有 HTML 则直接使用，否则 requests 抓取。
    - 返回 {"cleaned_text": str, "extraction_status": "ok"|"fallback"|"failed"}
    """
    if html is None:
        html = _fetch_html(url)

    if not html:
        return {"cleaned_text": "", "raw_text": "", "extraction_status": "failed"}

    # 尝试 trafilatura
    text = _try_trafilatura(html, url)
    if text and len(text) > 100:
        return {"cleaned_text": text, "raw_text": text, "extraction_status": "ok"}

    # 兜底 readability + BeautifulSoup
    text = _try_readability(html)
    if text and len(text) > 50:
        return {"cleaned_text": text, "raw_text": text, "extraction_status": "fallback"}

    return {"cleaned_text": "", "raw_text": "", "extraction_status": "failed"}


def _fetch_html(url: str) -> str:
    try:
        resp = requests.get(url, timeout=TIMEOUT, headers=HEADERS)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        logger.debug(f"HTTP fetch failed for {url}: {e}")
        return ""


def _try_trafilatura(html: str, url: str = "") -> str:
    try:
        import trafilatura
        text = trafilatura.extract(
            html,
            url=url or None,
            include_comments=False,
            include_tables=True,
            favor_recall=True,
        )
        return text or ""
    except Exception as e:
        logger.debug(f"trafilatura failed: {e}")
        return ""


def _try_readability(html: str) -> str:
    try:
        from readability import Document
        doc = Document(html)
        summary_html = doc.summary()
        soup = BeautifulSoup(summary_html, "html.parser")
        return soup.get_text(separator="\n", strip=True)
    except Exception as e:
        logger.debug(f"readability failed: {e}")
        return ""
