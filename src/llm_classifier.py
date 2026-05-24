"""
llm_classifier.py — 使用 tool-calling + 廉价模型（Haiku / GPT-4o-mini）分类文章。
无 API key 时自动降级为纯规则模式。
"""
import json
import logging
import time
from typing import Optional

from . import config_loader
from .database import Database

logger = logging.getLogger(__name__)

VALID_TOPICS = {f"T{i:02d}" for i in range(1, 23)}

# ─── Tool 定义 ────────────────────────────────────────────────────────────────

CLASSIFY_TOOL_ANTHROPIC = {
    "name": "classify_article",
    "description": "对中国经济文章进行分类打分，返回结构化评估结果",
    "input_schema": {
        "type": "object",
        "properties": {
            "keep": {"type": "boolean", "description": "是否保留此文章"},
            "primary_topic": {
                "type": "string",
                "enum": [f"T{i:02d}" for i in range(1, 23)],
                "description": "主主题 ID",
            },
            "secondary_topics": {
                "type": "array",
                "items": {"type": "string", "enum": [f"T{i:02d}" for i in range(1, 23)]},
                "description": "副主题 ID 列表（可为空）",
            },
            "china_relevance_score": {"type": "number", "minimum": 0, "maximum": 1},
            "economic_relevance_score": {"type": "number", "minimum": 0, "maximum": 1},
            "originality_score": {"type": "number", "minimum": 0, "maximum": 1},
            "expert_or_fact_score": {"type": "number", "minimum": 0, "maximum": 1},
            "noise_score": {"type": "number", "minimum": 0, "maximum": 1},
            "has_expert_opinion": {"type": "boolean"},
            "has_latest_economic_fact": {"type": "boolean"},
            "expert_names": {"type": "array", "items": {"type": "string"}},
            "institutions": {"type": "array", "items": {"type": "string"}},
            "key_facts": {"type": "array", "items": {"type": "string"}},
            "expert_viewpoints": {"type": "array", "items": {"type": "string"}},
            "summary": {"type": "string", "description": "50-100字中文摘要"},
            "reason_for_keep_or_reject": {"type": "string", "description": "保留或拒绝的原因"},
        },
        "required": [
            "keep", "primary_topic", "china_relevance_score",
            "economic_relevance_score", "noise_score",
            "has_expert_opinion", "has_latest_economic_fact",
            "summary", "reason_for_keep_or_reject",
        ],
    },
}

CLASSIFY_TOOL_OPENAI = {
    "type": "function",
    "function": {
        "name": "classify_article",
        "description": CLASSIFY_TOOL_ANTHROPIC["description"],
        "parameters": CLASSIFY_TOOL_ANTHROPIC["input_schema"],
    },
}


def classify_articles(db: Database) -> dict:
    """
    对 rule_keep=1 且尚未 LLM 分类的文章做分类。
    无 API key 时降级为规则模式。
    """
    provider = config_loader.get_env("LLM_PROVIDER", "anthropic").lower()
    model = config_loader.get_env("LLM_MODEL", "claude-haiku-4-5-20251001")
    anthropic_key = config_loader.get_env("ANTHROPIC_API_KEY")
    openai_key = config_loader.get_env("OPENAI_API_KEY")

    has_key = (provider == "anthropic" and anthropic_key) or \
              (provider == "openai" and openai_key)

    if not has_key:
        logger.info("No API key found. Using rule-only mode for classification.")
        return _rule_only_finalize(db)

    candidates = db.get_rule_candidates()
    if not candidates:
        logger.info("No articles need LLM classification.")
        return {"mode": "llm", "total": 0, "classified": 0, "failed": 0}

    logger.info(f"LLM classifying {len(candidates)} articles via {provider}/{model}")
    system_prompt = config_loader.load_classify_prompt()
    max_chars = config_loader.get_max_chars_for_llm()

    classified = 0
    failed = 0

    for article in candidates:
        try:
            result = _classify_one(
                article, system_prompt, provider, model,
                anthropic_key, openai_key, max_chars
            )
            if result:
                _save_result(db, article["id"], result)
                classified += 1
            else:
                failed += 1
        except Exception as e:
            logger.error(f"LLM classify failed for article {article['id']}: {e}")
            failed += 1
        time.sleep(0.3)  # 避免 rate limit

    logger.info(f"LLM classification done: {classified} classified, {failed} failed")
    return {"mode": "llm", "total": len(candidates), "classified": classified, "failed": failed}


def _classify_one(
    article: dict, system_prompt: str,
    provider: str, model: str,
    anthropic_key: str, openai_key: str,
    max_chars: int,
) -> Optional[dict]:
    user_text = _build_user_message(article, max_chars)

    if provider == "anthropic" and anthropic_key:
        return _call_anthropic(system_prompt, user_text, model, anthropic_key)
    elif provider == "openai" and openai_key:
        return _call_openai(system_prompt, user_text, model, openai_key)
    return None


def _call_anthropic(system_prompt: str, user_text: str, model: str, api_key: str) -> Optional[dict]:
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model,
            max_tokens=1500,
            system=system_prompt,
            tools=[CLASSIFY_TOOL_ANTHROPIC],
            tool_choice={"type": "tool", "name": "classify_article"},
            messages=[{"role": "user", "content": user_text}],
        )
        for block in response.content:
            if block.type == "tool_use" and block.name == "classify_article":
                return _validate_result(block.input)
    except Exception as e:
        logger.error(f"Anthropic API error: {e}")
    return None


def _call_openai(system_prompt: str, user_text: str, model: str, api_key: str) -> Optional[dict]:
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
            tools=[CLASSIFY_TOOL_OPENAI],
            tool_choice={"type": "function", "function": {"name": "classify_article"}},
            temperature=0.2,
        )
        for choice in response.choices:
            for tc in (choice.message.tool_calls or []):
                if tc.function.name == "classify_article":
                    data = json.loads(tc.function.arguments)
                    return _validate_result(data)
    except Exception as e:
        logger.error(f"OpenAI API error: {e}")
    return None


def _build_user_message(article: dict, max_chars: int) -> str:
    text = article.get("cleaned_text") or article.get("rss_summary") or ""
    text = text[:max_chars]
    return (
        f"标题：{article.get('title', '')}\n"
        f"来源：{article.get('source', '')}\n"
        f"作者：{article.get('author', '')}\n"
        f"发布时间：{article.get('published_at', '')}\n"
        f"摘要：{article.get('rss_summary', '')[:500]}\n\n"
        f"正文：\n{text}"
    )


def _validate_result(data: dict) -> dict:
    """校验并清理 LLM 返回的分类结果。"""
    # 确保必要字段存在
    result = {
        "keep": bool(data.get("keep", False)),
        "primary_topic": data.get("primary_topic", "T01"),
        "secondary_topics": [t for t in data.get("secondary_topics", []) if t in VALID_TOPICS],
        "china_relevance_score": _clamp(data.get("china_relevance_score", 0.0)),
        "economic_relevance_score": _clamp(data.get("economic_relevance_score", 0.0)),
        "originality_score": _clamp(data.get("originality_score", 0.5)),
        "expert_or_fact_score": _clamp(data.get("expert_or_fact_score", 0.0)),
        "noise_score": _clamp(data.get("noise_score", 0.0)),
        "has_expert_opinion": bool(data.get("has_expert_opinion", False)),
        "has_latest_economic_fact": bool(data.get("has_latest_economic_fact", False)),
        "expert_names": data.get("expert_names", []),
        "institutions": data.get("institutions", []),
        "key_facts": data.get("key_facts", []),
        "expert_viewpoints": data.get("expert_viewpoints", []),
        "summary": str(data.get("summary", ""))[:500],
        "reason_for_keep_or_reject": str(data.get("reason_for_keep_or_reject", ""))[:500],
    }
    # 校验 primary_topic
    if result["primary_topic"] not in VALID_TOPICS:
        result["primary_topic"] = "T01"
    return result


def _save_result(db: Database, article_id: int, result: dict):
    """将分类结果写入数据库。"""
    db.update_article(
        article_id,
        llm_result_json=json.dumps(result, ensure_ascii=False),
        china_relevance_score=result["china_relevance_score"],
        economic_relevance_score=result["economic_relevance_score"],
        originality_score=result["originality_score"],
        expert_or_fact_score=result["expert_or_fact_score"],
        noise_score=result["noise_score"],
        has_expert_opinion=1 if result["has_expert_opinion"] else 0,
        has_latest_economic_fact=1 if result["has_latest_economic_fact"] else 0,
        expert_names=json.dumps(result["expert_names"], ensure_ascii=False),
        institutions=json.dumps(result["institutions"], ensure_ascii=False),
        key_facts=json.dumps(result["key_facts"], ensure_ascii=False),
        expert_viewpoints=json.dumps(result["expert_viewpoints"], ensure_ascii=False),
        llm_summary=result["summary"],
        reason_for_keep=result["reason_for_keep_or_reject"],
        primary_topic=result["primary_topic"],
        secondary_topics=json.dumps(result["secondary_topics"], ensure_ascii=False),
    )


def _rule_only_finalize(db: Database) -> dict:
    """
    无 API key：对 rule_keep=1 的文章直接用规则分数决定 final_keep。
    """
    candidates = db.get_rule_candidates()
    for article in candidates:
        db.update_article(
            article["id"],
            llm_result_json=None,
            # 保留规则阶段写入的分数，不再覆盖
        )
    logger.info(f"rule-only mode: {len(candidates)} articles finalized by rules")
    return {"mode": "rule_only", "total": len(candidates), "classified": 0, "failed": 0}


def _clamp(v, lo: float = 0.0, hi: float = 1.0) -> float:
    try:
        return max(lo, min(hi, float(v)))
    except (TypeError, ValueError):
        return 0.0
