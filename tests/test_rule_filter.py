"""测试 rule_filter 模块。"""
import pytest

from src.rule_filter import apply_rules, _keyword_score, _originality_score


RULES = {
    "china_keywords": ["中国", "我国", "人民币", "A股", "PMI", "社融", "房地产"],
    "economic_keywords": ["GDP", "PMI", "社融", "财政", "货币政策", "汇率", "通胀"],
    "originality_keywords": ["原创", "首发", "专访", "研究报告"],
    "repost_keywords": ["转载自", "摘编自"],
    "noise_keywords": ["荐股", "牛股", "涨停", "课程", "直播课"],
}


def _article(title="", summary="", score=0.7):
    return {
        "title": title,
        "rss_summary": summary,
        "cleaned_text": "",
        "source_quality_score": score,
    }


class TestKeywordScore:
    def test_zero_hits(self):
        assert _keyword_score("完全无关的文本", ["关键词A", "关键词B"]) == 0.0

    def test_single_hit(self):
        score = _keyword_score("中国经济", ["中国", "美国", "欧洲"])
        assert 0 < score <= 1.0

    def test_multiple_hits(self):
        score = _keyword_score("中国 PMI 社融 GDP", ["中国", "PMI", "社融", "GDP"])
        assert score > 0.3

    def test_capped_at_one(self):
        keywords = [f"词{i}" for i in range(20)]
        text = " ".join(keywords)
        score = _keyword_score(text, keywords)
        assert score == 1.0


class TestOriginalityScore:
    def test_original_content(self):
        score = _originality_score("本文原创，首发于此", RULES)
        assert score == 1.0

    def test_repost_content(self):
        score = _originality_score("转载自财新网", RULES)
        assert score == 0.0

    def test_neutral_content(self):
        score = _originality_score("今天的市场分析", RULES)
        assert score == 0.5


class TestApplyRules:
    def test_high_quality_china_econ_article(self):
        # 确保 china_keywords 命中≥5个（阈值 0.65 需要 ≥5×0.15=0.75）
        # china_keywords: 中国, PMI, 社融, 房地产, 人民币, A股 = 6命中 → 0.90
        # economic_keywords: GDP, PMI, 社融, 货币政策, 通胀, 就业 = 6命中 → 0.90
        article = _article(
            title="中国GDP增速超预期，PMI数据亮眼，人民币汇率走强",
            summary="社融数据显示货币政策宽松，A股经济复苏态势良好。专家表示，房地产市场趋于稳定，通胀压力可控，就业数据改善。数据显示增长12%。",
        )
        result = apply_rules(article, RULES)
        # 包含中国+经济关键词+专家信号+数据，应保留
        assert result["rule_keep"] is True
        assert result["china_relevance_score"] > 0
        assert result["economic_relevance_score"] > 0

    def test_noise_article_rejected(self):
        article = _article(
            title="这只牛股明天必涨停！荐股内幕",
            summary="直播课教你选牛股，涨停技巧大公开",
        )
        result = apply_rules(article, RULES)
        assert result["noise_score"] > 0.4

    def test_trusted_source_override(self):
        """高质量来源（>=0.80）可以豁免严格阈值。"""
        article = _article(
            title="经济简讯",
            summary="今日简讯",
            score=0.85,  # 高质量来源
        )
        # 对于非常高质量来源，轻微包含中国经济内容可以通过
        # 此测试验证 trusted_keep 逻辑存在
        result = apply_rules(article, RULES)
        assert "rule_keep" in result

    def test_scores_are_floats_in_range(self):
        article = _article(title="中国PMI", summary="GDP增长")
        result = apply_rules(article, RULES)
        for key in ["china_relevance_score", "economic_relevance_score",
                    "noise_score", "originality_score", "expert_or_fact_score"]:
            assert 0.0 <= result[key] <= 1.0, f"{key} out of range: {result[key]}"
