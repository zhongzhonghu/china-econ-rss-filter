"""测试 scoring 模块。"""
import pytest
from datetime import datetime, timezone, timedelta

from src.scoring import compute_priority_score, freshness_score, apply_keep_rule


def _article(**kwargs):
    defaults = {
        "china_relevance_score": 0.7,
        "economic_relevance_score": 0.7,
        "expert_or_fact_score": 0.7,
        "originality_score": 0.5,
        "source_quality_score": 0.7,
        "noise_score": 0.1,
        "has_expert_opinion": 1,
        "has_latest_economic_fact": 1,
        "published_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00"),
    }
    defaults.update(kwargs)
    return defaults


class TestFreshnessScore:
    def test_just_published(self):
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
        assert freshness_score(now) == 1.0

    def test_12h_ago(self):
        dt = datetime.now(timezone.utc) - timedelta(hours=12)
        s = dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")
        assert freshness_score(s) == 1.0

    def test_48h_ago(self):
        dt = datetime.now(timezone.utc) - timedelta(hours=48)
        s = dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")
        score = freshness_score(s)
        assert 0.0 < score < 1.0

    def test_8_days_ago(self):
        dt = datetime.now(timezone.utc) - timedelta(days=8)
        s = dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")
        assert freshness_score(s) == 0.0

    def test_none_returns_midpoint(self):
        assert freshness_score(None) == 0.5

    def test_empty_string_returns_midpoint(self):
        assert freshness_score("") == 0.5


class TestComputePriorityScore:
    def test_high_quality_article(self):
        a = _article(
            china_relevance_score=0.9,
            economic_relevance_score=0.85,
            expert_or_fact_score=0.8,
            originality_score=0.9,
            source_quality_score=0.85,
            noise_score=0.05,
        )
        score, level = compute_priority_score(a)
        assert score >= 0.75
        assert level == "High"

    def test_medium_quality_article(self):
        a = _article(
            china_relevance_score=0.7,
            economic_relevance_score=0.65,
            expert_or_fact_score=0.65,
            originality_score=0.5,
            source_quality_score=0.6,
            noise_score=0.2,
        )
        score, level = compute_priority_score(a)
        assert 0.55 <= score < 0.75
        assert level == "Medium"

    def test_score_clamped_to_zero(self):
        a = _article(
            china_relevance_score=0.0,
            economic_relevance_score=0.0,
            expert_or_fact_score=0.0,
            originality_score=0.0,
            source_quality_score=0.0,
            noise_score=1.0,
        )
        score, _ = compute_priority_score(a)
        assert score == 0.0

    def test_score_clamped_to_one(self):
        a = _article(
            china_relevance_score=1.0,
            economic_relevance_score=1.0,
            expert_or_fact_score=1.0,
            originality_score=1.0,
            source_quality_score=1.0,
            noise_score=0.0,
        )
        score, _ = compute_priority_score(a)
        assert score == 1.0

    def test_priority_levels(self):
        high_article = _article(china_relevance_score=0.95, economic_relevance_score=0.9,
                                 expert_or_fact_score=0.9, originality_score=0.9,
                                 source_quality_score=0.9, noise_score=0.02)
        low_article = _article(china_relevance_score=0.3, economic_relevance_score=0.3,
                                expert_or_fact_score=0.3, originality_score=0.3,
                                source_quality_score=0.3, noise_score=0.5)
        _, high_level = compute_priority_score(high_article)
        _, low_level = compute_priority_score(low_article)
        assert high_level == "High"
        assert low_level == "Low"


class TestApplyKeepRule:
    def test_keeps_good_article(self):
        a = _article(
            china_relevance_score=0.7,
            economic_relevance_score=0.65,
            expert_or_fact_score=0.65,
            noise_score=0.2,
            has_expert_opinion=1,
            has_latest_economic_fact=1,
        )
        assert apply_keep_rule(a) is True

    def test_rejects_low_china_score(self):
        a = _article(china_relevance_score=0.3)
        assert apply_keep_rule(a) is False

    def test_rejects_high_noise(self):
        a = _article(noise_score=0.8)
        assert apply_keep_rule(a) is False
