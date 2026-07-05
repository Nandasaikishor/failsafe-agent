"""Tests for the feedback correction module."""

from failsafe.feedback.correction import CorrectionState, FeedbackCorrector
from failsafe.schema import (
    CollectorConfiguration,
    CollectorType,
    DimensionScore,
    ErrorTag,
    FieldSpec,
    ListConfig,
    QualityReport,
    TaskRepresentation,
)


def _make_config() -> CollectorConfiguration:
    task = TaskRepresentation(
        description="Test task",
        source="https://example.com",
        fields=[FieldSpec(name="title", type="string")],
        collector_type=CollectorType.LIST,
    )
    collector = ListConfig(
        list_url="https://example.com",
        item_selector=".item",
        title_selector="h3",
        link_selector="a",
    )
    return CollectorConfiguration(task=task, collectors=[collector])


def _make_report(errors: list[ErrorTag], score: float = 0.3) -> QualityReport:
    return QualityReport(
        scores=DimensionScore(structure=0.4, content=0.3, relevance=0.2),
        composite_score=score,
        passed=False,
        error_tags=errors,
        correction_hints=["Selectors not matching"],
        sample_data=[{"title": ""}],
    )


def test_no_correction_when_no_errors():
    corrector = FeedbackCorrector()
    config = _make_config()
    report = QualityReport(
        scores=DimensionScore(structure=1.0, content=1.0, relevance=1.0),
        composite_score=0.9,
        passed=True,
        error_tags=[],
    )
    state = CorrectionState()

    result = corrector.compute_feedback(config, report, state)
    assert result is None


def test_produces_feedback_on_parse_error():
    corrector = FeedbackCorrector()
    config = _make_config()
    report = _make_report([ErrorTag.PARSE_ERROR, ErrorTag.SCHEMA_ERROR])
    state = CorrectionState()

    feedback = corrector.compute_feedback(config, report, state)
    assert feedback is not None
    assert feedback.error_tag == ErrorTag.PARSE_ERROR
    assert state.round == 1


def test_priority_order():
    corrector = FeedbackCorrector()
    config = _make_config()
    report = _make_report([ErrorTag.LOW_RELEVANCE, ErrorTag.SCHEMA_ERROR])
    state = CorrectionState()

    feedback = corrector.compute_feedback(config, report, state)
    assert feedback.error_tag == ErrorTag.SCHEMA_ERROR


def test_max_rounds_respected():
    corrector = FeedbackCorrector(max_rounds=2)
    config = _make_config()
    report = _make_report([ErrorTag.PARSE_ERROR])
    state = CorrectionState(round=2)

    feedback = corrector.compute_feedback(config, report, state)
    assert feedback is None


def test_blacklist_grows():
    corrector = FeedbackCorrector()
    config = _make_config()
    # Use empty sample_data so item_selector gets blacklisted
    report = QualityReport(
        scores=DimensionScore(structure=0.4, content=0.3, relevance=0.2),
        composite_score=0.3,
        passed=False,
        error_tags=[ErrorTag.PARSE_ERROR],
        correction_hints=["Selectors not matching"],
        sample_data=[],
    )
    state = CorrectionState()

    corrector.compute_feedback(config, report, state)
    assert len(state.blacklist) > 0
    assert state.round == 1
