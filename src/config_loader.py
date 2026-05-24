"""
config_loader.py — 加载环境变量和 YAML 配置文件。
所有路径基于项目根目录（本文件的父目录的父目录）相对解析。
"""
import os
import logging
from pathlib import Path

import yaml
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# 项目根目录（src/ 的上级）
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 标准路径常量
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "output"
DOCS_DIR = PROJECT_ROOT / "docs"
PROMPTS_DIR = PROJECT_ROOT / "prompts"


def load_env() -> None:
    """加载 .env 文件（如果存在）。"""
    env_path = PROJECT_ROOT / ".env"
    load_dotenv(env_path)


def get_env(key: str, default: str = "") -> str:
    """获取环境变量，不存在时返回默认值。"""
    return os.environ.get(key, default)


def load_yaml(filename: str) -> dict:
    """从 config/ 目录加载 YAML 文件。"""
    path = CONFIG_DIR / filename
    if not path.exists():
        logger.warning(f"Config file not found: {path}")
        return {}
    with open(path, "r", encoding="utf-8") as f:
        result = yaml.safe_load(f) or {}
    return result


def load_topics() -> dict:
    """返回主题 ID -> 描述 的字典。"""
    return load_yaml("topics.yaml")


def load_filter_rules() -> dict:
    """返回过滤规则字典（各类关键词列表）。"""
    return load_yaml("filter_rules.yaml")


def load_feeds() -> list:
    """返回 feeds.yaml 中的 feeds 列表，不存在时返回空列表。"""
    data = load_yaml("feeds.yaml")
    return data.get("feeds", [])


def load_classify_prompt() -> str:
    """加载 LLM 分类提示词。"""
    path = PROMPTS_DIR / "classify_article.md"
    if not path.exists():
        logger.warning(f"Classify prompt not found: {path}")
        return ""
    return path.read_text(encoding="utf-8")


def get_database_path() -> Path:
    """返回 SQLite 数据库路径（可被 .env 中 DATABASE_PATH 覆盖）。"""
    db_env = get_env("DATABASE_PATH")
    if db_env:
        p = Path(db_env)
        if not p.is_absolute():
            p = PROJECT_ROOT / p
        return p
    return DATA_DIR / "articles.sqlite"


def get_max_articles() -> int:
    """每次 run 最多处理的文章数。"""
    val = get_env("MAX_ARTICLES_PER_RUN", "200")
    try:
        return int(val)
    except ValueError:
        return 200


def get_max_chars_for_llm() -> int:
    """发送给 LLM 的文章正文最大字符数。"""
    val = get_env("MAX_ARTICLE_CHARS_FOR_LLM", "12000")
    try:
        return int(val)
    except ValueError:
        return 12000


def get_public_feed_base_url() -> str:
    """GitHub Pages 基础 URL，可选。"""
    return get_env("PUBLIC_FEED_BASE_URL", "")


def ensure_dirs() -> None:
    """确保运行时需要的目录存在。"""
    for d in [DATA_DIR, OUTPUT_DIR, DOCS_DIR]:
        d.mkdir(parents=True, exist_ok=True)
