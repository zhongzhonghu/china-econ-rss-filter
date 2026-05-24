"""
publish_assets.py — 将 output/selected_feed.xml 拷贝到 docs/，生成 index.html 和 feed_info.json。
"""
import json
import logging
import shutil
from datetime import datetime

from . import config_loader
from .database import Database

logger = logging.getLogger(__name__)


def publish(db: Database = None) -> dict:
    """
    1. 创建 docs/ 目录
    2. 拷贝 output/selected_feed.xml → docs/selected_feed.xml
    3. 生成 docs/index.html
    4. 生成 docs/feed_info.json
    """
    output_dir = config_loader.OUTPUT_DIR
    docs_dir = config_loader.DOCS_DIR
    docs_dir.mkdir(parents=True, exist_ok=True)

    feed_src = output_dir / "selected_feed.xml"
    feed_dst = docs_dir / "selected_feed.xml"

    if not feed_src.exists():
        logger.warning(f"selected_feed.xml not found at {feed_src}, skipping copy.")
        article_count = 0
    else:
        shutil.copy2(feed_src, feed_dst)
        logger.info(f"Copied {feed_src} → {feed_dst}")
        article_count = _count_items(feed_dst)

    base_url = config_loader.get_public_feed_base_url().rstrip("/")
    feed_url = f"{base_url}/selected_feed.xml" if base_url else "selected_feed.xml"
    build_time = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    _write_index_html(docs_dir / "index.html", build_time, feed_url, article_count)
    _write_feed_info(docs_dir / "feed_info.json", build_time, feed_url, article_count, base_url)

    logger.info(f"publish-assets done: docs/ updated, {article_count} articles in feed")
    return {"article_count": article_count, "feed_url": feed_url}


def _count_items(feed_path) -> int:
    try:
        text = feed_path.read_text(encoding="utf-8")
        return text.count("<item>")
    except Exception:
        return 0


def _write_index_html(path, build_time: str, feed_url: str, article_count: int):
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>中国经济精选 RSS</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
           max-width: 680px; margin: 60px auto; padding: 0 24px; color: #1a1a1a; }}
    h1 {{ font-size: 1.8rem; margin-bottom: 0.3rem; }}
    .subtitle {{ color: #555; margin-bottom: 2rem; }}
    .meta {{ background: #f5f5f5; padding: 16px; border-radius: 8px; margin-bottom: 1.5rem; }}
    .meta p {{ margin: 4px 0; font-size: 0.92rem; }}
    .feed-link {{ display: inline-block; background: #e8501d; color: #fff;
                  padding: 10px 20px; border-radius: 6px; text-decoration: none;
                  font-weight: 600; margin-bottom: 1.5rem; }}
    .feed-link:hover {{ background: #c43a12; }}
    .desc {{ line-height: 1.7; color: #333; }}
    .desc ul {{ padding-left: 1.2rem; }}
    footer {{ margin-top: 3rem; color: #999; font-size: 0.85rem; }}
  </style>
</head>
<body>
  <h1>🇨🇳 中国经济精选 RSS</h1>
  <p class="subtitle">China Economic RSS Filter — AI 精选中国经济新闻与分析</p>

  <div class="meta">
    <p>📅 最新构建时间：{build_time}</p>
    <p>📰 本次精选文章数：{article_count} 篇（24小时内，最多200条）</p>
  </div>

  <a class="feed-link" href="selected_feed.xml">订阅 RSS Feed</a>

  <div class="desc">
    <p>本 RSS Feed 自动筛选以下类型的中国经济文章：</p>
    <ul>
      <li>与中国经济、政策、金融市场、产业相关</li>
      <li>包含专家观点、最新官方数据或深度分析</li>
      <li>过滤广告、荐股、低质转载等噪声内容</li>
    </ul>
    <p>支持 Folo、Feedly、Inoreader、FreshRSS 等所有标准 RSS 阅读器。</p>
  </div>

  <footer>
    <p>由 <a href="https://github.com/anthropics/claude-code">Claude Code</a> 构建 ·
    <a href="selected_feed.xml">RSS 2.0 Feed</a></p>
  </footer>
</body>
</html>
"""
    path.write_text(html, encoding="utf-8")
    logger.info(f"Written: {path}")


def _write_feed_info(path, build_time: str, feed_url: str, article_count: int, base_url: str):
    info = {
        "project": "china-econ-rss-filter",
        "last_build": build_time,
        "total_articles": article_count,
        "feed_url": feed_url,
        "base_url": base_url,
    }
    path.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"Written: {path}")
