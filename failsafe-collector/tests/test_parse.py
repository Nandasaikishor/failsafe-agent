"""Tests for the parse utility functions."""

from failsafe.utils.parse import extract_json_path, map_fields, parse_csv_text


def test_json_path_simple():
    data = {"results": [{"name": "Alice"}, {"name": "Bob"}]}
    assert extract_json_path(data, "$.results") == [{"name": "Alice"}, {"name": "Bob"}]


def test_json_path_nested():
    data = {"data": {"items": [{"id": 1}]}}
    assert extract_json_path(data, "$.data.items") == [{"id": 1}]


def test_json_path_root():
    data = [1, 2, 3]
    assert extract_json_path(data, "$") == [1, 2, 3]


def test_json_path_with_index():
    data = {"results": [{"name": "Alice"}, {"name": "Bob"}]}
    assert extract_json_path(data, "$.results[0].name") == "Alice"


def test_json_path_missing():
    data = {"foo": "bar"}
    assert extract_json_path(data, "$.missing.path") is None


def test_map_fields():
    record = {"product_name": "Widget", "unit_price": 9.99, "category": {"name": "Tools"}}
    mappings = {"name": "product_name", "price": "unit_price"}
    result = map_fields(record, mappings)
    assert result == {"name": "Widget", "price": 9.99}


def test_map_fields_empty():
    record = {"a": 1, "b": 2}
    assert map_fields(record, {}) == {"a": 1, "b": 2}


def test_parse_csv():
    text = "name,age,city\nAlice,30,NYC\nBob,25,SF"
    records = parse_csv_text(text)
    assert len(records) == 2
    assert records[0] == {"name": "Alice", "age": "30", "city": "NYC"}
