"""Tests for the quality scoring module."""

from failsafe.collectors.base import CollectionResult
from failsafe.quality.scorer import QualityScorer
from failsafe.schema import ErrorTag, FieldSpec, ValidationThresholds


def test_perfect_score():
    fields = [
        FieldSpec(name="title", type="string"),
        FieldSpec(name="url", type="string"),
        FieldSpec(name="date", type="string"),
    ]
    records = [
        {"title": "Article 1", "url": "https://example.com/1", "date": "2024-01-01"},
        {"title": "Article 2", "url": "https://example.com/2", "date": "2024-01-02"},
    ]
    result = CollectionResult(records=records)
    scorer = QualityScorer()
    report = scorer.assess(result, fields)

    assert report.composite_score > 0.8
    assert report.passed is True
    assert report.error_tags == []


def test_missing_fields():
    fields = [
        FieldSpec(name="title", type="string"),
        FieldSpec(name="url", type="string"),
        FieldSpec(name="date", type="string"),
        FieldSpec(name="author", type="string"),
        FieldSpec(name="category", type="string"),
    ]
    records = [
        {"title": "Article 1", "url": "https://example.com/1"},
        {"title": "Article 2", "url": "https://example.com/2"},
    ]
    result = CollectionResult(records=records)
    scorer = QualityScorer()
    report = scorer.assess(result, fields)

    assert report.scores.structure < 1.0
    assert report.scores.structure == 2 / 5  # 2 out of 5 fields present


def test_empty_results_fails():
    fields = [FieldSpec(name="title", type="string")]
    result = CollectionResult(records=[], errors=["HTTP 404"])
    scorer = QualityScorer()
    report = scorer.assess(result, fields)

    # attachment defaults to 1.0 when none expected, so score = 0.10 * 1.0 = 0.10
    assert report.composite_score <= 0.10
    assert report.passed is False
    assert ErrorTag.SOURCE_DEFECT in report.error_tags


def test_execution_score_partial():
    fields = [FieldSpec(name="title", type="string")]
    records = [{"title": "Article 1"}]
    result = CollectionResult(records=records, errors=["Timeout on page 3"])
    scorer = QualityScorer()
    report = scorer.assess(result, fields)

    assert report.scores.execution == 0.5


def test_custom_weights():
    thresholds = ValidationThresholds(
        structure_weight=0.5,
        content_weight=0.2,
        relevance_weight=0.1,
        attachment_weight=0.1,
        execution_weight=0.1,
    )
    fields = [FieldSpec(name="title", type="string")]
    records = [{"title": "Test"}]
    result = CollectionResult(records=records)

    scorer = QualityScorer(thresholds)
    report = scorer.assess(result, fields)
    assert report.passed is True


def test_pass_threshold():
    fields = [
        FieldSpec(name="title", type="string"),
        FieldSpec(name="url", type="string"),
    ]
    records = [{"title": "Test", "url": "https://test.com"}]
    result = CollectionResult(records=records)

    scorer = QualityScorer()
    report = scorer.assess(result, fields)
    assert report.composite_score >= 0.60
    assert report.passed is True
