"""
main.py — CLI 主入口。
用法：python -m src.main <command>
"""
import argparse
import logging
import sys
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("main")


def cmd_import_sources():
    from . import config_loader
    from .excel_importer import import_sources

    config_loader.load_env()
    config_loader.ensure_dirs()

    excel_path = config_loader.CONFIG_DIR / "rss_sources.xlsx"
    feeds_yaml = config_loader.CONFIG_DIR / "feeds.yaml"
    report = config_loader.OUTPUT_DIR / "rss_sources_validation.md"

    result = import_sources(excel_path, feeds_yaml, report)
    logger.info(f"import-sources: {result}")
    return result


def cmd_fetch():
    from . import config_loader
    from .database import Database
    from .fetch_feeds import fetch_all

    config_loader.load_env()
    config_loader.ensure_dirs()

    with Database() as db:
        result = fetch_all(db)
    logger.info(f"fetch: {result}")
    return result


def cmd_classify():
    from . import config_loader
    from .database import Database
    from .deduplicate import run_deduplication
    from .rule_filter import run_rule_filter
    from .extract_article import extract_batch
    from .llm_classifier import classify_articles
    from .scoring import compute_all_scores

    config_loader.load_env()
    config_loader.ensure_dirs()

    with Database() as db:
        logger.info("Step: deduplication")
        removed = run_deduplication(db)
        logger.info(f"  removed {removed} duplicates")

        logger.info("Step: rule filter (title + rss_summary)")
        rule_stats = run_rule_filter(db)
        logger.info(f"  {rule_stats}")

        logger.info("Step: extract article text (rule_keep=1 candidates)")
        extract_stats = extract_batch(db)
        logger.info(f"  {extract_stats}")

        logger.info("Step: LLM classification")
        llm_stats = classify_articles(db)
        logger.info(f"  {llm_stats}")

        logger.info("Step: scoring")
        score_stats = compute_all_scores(db)
        logger.info(f"  {score_stats}")

    return {
        "dedup_removed": removed,
        "rule": rule_stats,
        "extract": extract_stats,
        "llm": llm_stats,
        "scoring": score_stats,
    }


def cmd_digest():
    from . import config_loader
    from .database import Database
    from .digest_generator import generate_digest

    config_loader.load_env()
    config_loader.ensure_dirs()

    with Database() as db:
        result = generate_digest(db)
    logger.info(f"digest: {result}")
    return result


def cmd_feed():
    from . import config_loader
    from .database import Database
    from .rss_feed_generator import generate_feed

    config_loader.load_env()
    config_loader.ensure_dirs()

    with Database() as db:
        result = generate_feed(db)
    logger.info(f"feed: {result}")
    return result


def cmd_publish_assets():
    from . import config_loader
    from .database import Database
    from .publish_assets import publish

    config_loader.load_env()
    config_loader.ensure_dirs()

    with Database() as db:
        result = publish(db)
    logger.info(f"publish-assets: {result}")
    return result


def cmd_run():
    """串联执行完整管道。"""
    from . import config_loader
    from .database import Database

    config_loader.load_env()
    config_loader.ensure_dirs()

    started = datetime.utcnow()

    with Database() as db:
        run_id = db.insert_run({"started_at": started.strftime("%Y-%m-%dT%H:%M:%SZ")})

    try:
        logger.info("=" * 50)
        logger.info("STEP 1/6: import-sources")
        import_result = cmd_import_sources()

        logger.info("=" * 50)
        logger.info("STEP 2/6: fetch")
        fetch_result = cmd_fetch()

        logger.info("=" * 50)
        logger.info("STEP 3/6: classify (dedup + rules + LLM + scoring)")
        classify_result = cmd_classify()

        logger.info("=" * 50)
        logger.info("STEP 4/6: digest")
        digest_result = cmd_digest()

        logger.info("=" * 50)
        logger.info("STEP 5/6: feed")
        feed_result = cmd_feed()

        logger.info("=" * 50)
        logger.info("STEP 6/6: publish-assets")
        publish_result = cmd_publish_assets()

        finished = datetime.utcnow()
        with Database() as db:
            db.update_run(
                run_id,
                finished_at=finished.strftime("%Y-%m-%dT%H:%M:%SZ"),
                total_fetched=fetch_result.get("total_fetched", 0),
                total_new=fetch_result.get("total_new", 0),
                total_rule_candidates=classify_result.get("rule", {}).get("kept", 0),
                total_llm_classified=classify_result.get("llm", {}).get("classified", 0),
                total_kept=digest_result.get("article_count", 0),
            )

        logger.info("=" * 50)
        logger.info("run COMPLETE")
        logger.info(f"  Fetched: {fetch_result.get('total_fetched', 0)}")
        logger.info(f"  New: {fetch_result.get('total_new', 0)}")
        logger.info(f"  Kept: {digest_result.get('article_count', 0)}")
        logger.info(f"  Feed articles (24h): {feed_result.get('article_count', 0)}")
        logger.info(f"  Docs: {config_loader.DOCS_DIR}")

    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        with Database() as db:
            db.update_run(
                run_id,
                finished_at=datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                notes=f"Failed: {e}",
            )
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="China Economic RSS Filter",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
命令说明：
  import-sources   从 config/rss_sources.xlsx 导入 RSS 源
  fetch            抓取 RSS 文章
  classify         去重 + 规则过滤 + LLM 分类 + 评分
  digest           生成 output/daily_digest.md 和 CSV
  feed             生成 output/selected_feed.xml
  publish-assets   将产物发布到 docs/（用于 GitHub Pages）
  run              执行以上全部步骤
        """,
    )
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("import-sources", help="从 Excel 导入 RSS 源")
    subparsers.add_parser("fetch", help="抓取 RSS 文章")
    subparsers.add_parser("classify", help="规则过滤 + LLM 分类 + 评分")
    subparsers.add_parser("digest", help="生成每日摘要")
    subparsers.add_parser("feed", help="生成 RSS XML")
    subparsers.add_parser("publish-assets", help="发布到 docs/")
    subparsers.add_parser("run", help="运行完整管道")

    args = parser.parse_args()

    dispatch = {
        "import-sources": cmd_import_sources,
        "fetch": cmd_fetch,
        "classify": cmd_classify,
        "digest": cmd_digest,
        "feed": cmd_feed,
        "publish-assets": cmd_publish_assets,
        "run": cmd_run,
    }

    if args.command in dispatch:
        dispatch[args.command]()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
