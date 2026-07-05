"""Manual/offline agent mode — generate configs without an API key.

This module allows generating configurations offline by providing
the LLM output directly (e.g., from Claude Code acting as the agent).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from failsafe.schema import (
    CollectorConfiguration,
    CollectorType,
    CollectionConstraints,
    FieldSpec,
    OutputFormat,
    SourceContext,
    TaskRepresentation,
    ValidationThresholds,
)


def create_config_from_dict(config_dict: dict) -> CollectorConfiguration:
    """Create a CollectorConfiguration from a raw dictionary."""
    return CollectorConfiguration.model_validate(config_dict)


def save_config(config: CollectorConfiguration, path: str) -> None:
    """Save configuration to a JSON file."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(config.model_dump(), f, indent=2, default=str)


def generate_task(
    description: str,
    source: str,
    collector_type: str,
    fields: list,
    max_pages: int = 5,
    rate_limit: float = 1.0,
) -> TaskRepresentation:
    """Helper to manually construct a TaskRepresentation."""
    ct = collector_type
    if isinstance(ct, str):
        if "+" in ct:
            ct = [CollectorType(t.strip()) for t in ct.split("+")]
        else:
            ct = CollectorType(ct)

    field_specs = []
    for f in fields:
        if isinstance(f, str):
            field_specs.append(FieldSpec(name=f))
        elif isinstance(f, dict):
            field_specs.append(FieldSpec(**f))
        else:
            field_specs.append(f)

    return TaskRepresentation(
        description=description,
        source=source,
        collector_type=ct,
        fields=field_specs,
        constraints=CollectionConstraints(
            max_pages=max_pages,
            rate_limit_seconds=rate_limit,
        ),
    )
