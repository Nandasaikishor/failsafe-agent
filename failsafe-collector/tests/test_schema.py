"""Tests for schema models."""

from failsafe.schema import (
    CollectorConfiguration,
    CollectorType,
    FieldSpec,
    ListConfig,
    SearchConfig,
    TaskRepresentation,
    ValidationThresholds,
)


def test_task_representation():
    task = TaskRepresentation(
        description="Collect news",
        source="https://example.com",
        fields=[FieldSpec(name="title", type="string")],
        collector_type=CollectorType.LIST,
        confidence=0.85,
    )
    assert task.collector_type == CollectorType.LIST
    assert task.confidence == 0.85


def test_task_with_composition():
    task = TaskRepresentation(
        description="Search and extract",
        source="https://example.com",
        fields=[],
        collector_type=[CollectorType.SEARCH, CollectorType.DETAIL],
    )
    assert isinstance(task.collector_type, list)
    assert len(task.collector_type) == 2


def test_list_config():
    config = ListConfig(
        list_url="https://example.com/news",
        item_selector=".news-item",
        title_selector="h2 a",
        link_selector="h2 a",
        page_param="page",
        max_pages=5,
    )
    assert config.collector_type == CollectorType.LIST
    assert config.start_page == 1


def test_search_config():
    config = SearchConfig(
        search_url="https://example.com/search",
        keywords=["test"],
        result_selector=".result",
        title_selector=".title",
        link_selector="a",
    )
    assert config.collector_type == CollectorType.SEARCH
    assert config.keyword_param == "q"


def test_collector_configuration():
    task = TaskRepresentation(
        description="Test",
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
    config = CollectorConfiguration(task=task, collectors=[collector])
    assert len(config.collectors) == 1
    assert config.validation.min_quality_score == 0.60


def test_validation_thresholds_sum_to_one():
    t = ValidationThresholds()
    total = (
        t.structure_weight + t.content_weight + t.relevance_weight
        + t.attachment_weight + t.execution_weight
    )
    assert abs(total - 1.0) < 0.001
