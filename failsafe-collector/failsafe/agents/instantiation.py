"""Collector Instantiation Agent.

Constrained to produce typed JSON configurations from templates.
Fills slot values (URLs, selectors, API parameters, field mappings, cleaning rules)
within the bounds of the template's slot space Theta_k.
"""

from __future__ import annotations

import json
from typing import Any

from failsafe.agents.llm import LLMClient
from failsafe.schema import (
    APIConfig,
    ActionStep,
    CollectorConfig,
    CollectorConfiguration,
    CollectorType,
    DetailConfig,
    FileConfig,
    FeedbackConstraint,
    InteractiveConfig,
    ListConfig,
    SearchConfig,
    TaskRepresentation,
    ValidationThresholds,
)

SYSTEM_PROMPT = """\
You are a Collector Instantiation Agent. Your role is to produce typed JSON collector
configurations that will be executed deterministically — no code generation.

## Constraints:
1. You MUST output valid JSON matching the schema for the specified collector type.
2. You MUST only use CSS selectors, JSON paths, and field mappings — NO executable code.
3. You MUST respect the source context (DOM structure, pagination, API availability).
4. Selectors must be specific enough to avoid false matches but robust to minor DOM changes.
5. Prefer ID and semantic class selectors over positional (nth-child) selectors.

## Collector Configuration Schemas:

### search
{search_url, keyword_param, keywords[], time_range_param, result_selector,
 title_selector, link_selector, next_page_selector, max_pages}

### list
{list_url, item_selector, title_selector, link_selector, date_selector,
 next_page_selector, page_param, start_page, max_pages}

### detail
{url_pattern, field_selectors: {field_name: css_selector}, content_selector,
 attachment_selector, date_format, encoding}

### api
{endpoint_url, method, headers, params, body, pagination_type, pagination_param,
 data_path, field_mappings: {target: source_path}, max_pages}

### interactive
{url, actions: [{action, selector, value, wait_ms}], result_selector,
 field_selectors: {field_name: css_selector}, wait_for_selector, screenshot}

### file
{file_url, file_type, sheet_name, start_row, header_row,
 field_mappings: {target: source_col}, encoding}

## Selector Conventions:
- For href extraction, prefix with "href:" e.g. "href:a.download-link"
- For attribute extraction, use "@selector|attribute" e.g. "@img.thumb|src"
- Regular selectors extract text content

Output a JSON array of collector configurations in execution order.
"""

CONFIG_SCHEMAS: dict[CollectorType, dict[str, Any]] = {
    CollectorType.SEARCH: {
        "type": "object",
        "required": ["search_url", "keywords", "result_selector", "title_selector", "link_selector"],
        "properties": {
            "search_url": {"type": "string"},
            "keyword_param": {"type": "string", "default": "q"},
            "keywords": {"type": "array", "items": {"type": "string"}},
            "time_range_param": {"type": ["string", "null"]},
            "result_selector": {"type": "string"},
            "title_selector": {"type": "string"},
            "link_selector": {"type": "string"},
            "next_page_selector": {"type": ["string", "null"]},
            "max_pages": {"type": "integer", "default": 5},
        },
    },
    CollectorType.LIST: {
        "type": "object",
        "required": ["list_url", "item_selector", "title_selector", "link_selector"],
        "properties": {
            "list_url": {"type": "string"},
            "item_selector": {"type": "string"},
            "title_selector": {"type": "string"},
            "link_selector": {"type": "string"},
            "date_selector": {"type": ["string", "null"]},
            "next_page_selector": {"type": ["string", "null"]},
            "page_param": {"type": ["string", "null"]},
            "start_page": {"type": "integer", "default": 1},
            "max_pages": {"type": "integer", "default": 10},
        },
    },
    CollectorType.DETAIL: {
        "type": "object",
        "required": ["field_selectors"],
        "properties": {
            "url_pattern": {"type": ["string", "null"]},
            "field_selectors": {"type": "object", "additionalProperties": {"type": "string"}},
            "content_selector": {"type": ["string", "null"]},
            "attachment_selector": {"type": ["string", "null"]},
            "date_format": {"type": ["string", "null"]},
            "encoding": {"type": "string", "default": "utf-8"},
        },
    },
    CollectorType.API: {
        "type": "object",
        "required": ["endpoint_url", "data_path"],
        "properties": {
            "endpoint_url": {"type": "string"},
            "method": {"type": "string", "default": "GET"},
            "headers": {"type": "object"},
            "params": {"type": "object"},
            "body": {"type": ["object", "null"]},
            "pagination_type": {"type": ["string", "null"]},
            "pagination_param": {"type": ["string", "null"]},
            "data_path": {"type": "string", "default": "$"},
            "field_mappings": {"type": "object"},
            "max_pages": {"type": "integer", "default": 10},
        },
    },
    CollectorType.INTERACTIVE: {
        "type": "object",
        "required": ["url", "actions", "result_selector", "field_selectors"],
        "properties": {
            "url": {"type": "string"},
            "actions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["action"],
                    "properties": {
                        "action": {"type": "string", "enum": ["click", "type", "wait", "scroll", "select"]},
                        "selector": {"type": ["string", "null"]},
                        "value": {"type": ["string", "null"]},
                        "wait_ms": {"type": "integer", "default": 1000},
                    },
                },
            },
            "result_selector": {"type": "string"},
            "field_selectors": {"type": "object"},
            "wait_for_selector": {"type": ["string", "null"]},
            "screenshot": {"type": "boolean", "default": False},
        },
    },
    CollectorType.FILE: {
        "type": "object",
        "required": ["file_url", "file_type"],
        "properties": {
            "file_url": {"type": "string"},
            "file_type": {"type": "string", "enum": ["pdf", "xlsx", "xls", "csv", "docx"]},
            "sheet_name": {"type": ["string", "null"]},
            "start_row": {"type": "integer", "default": 0},
            "header_row": {"type": ["integer", "null"], "default": 0},
            "field_mappings": {"type": "object"},
            "encoding": {"type": "string", "default": "utf-8"},
        },
    },
}


class InstantiationAgent:
    def __init__(self, llm: LLMClient | None = None):
        self.llm = llm or LLMClient()

    def instantiate(
        self,
        task: TaskRepresentation,
        feedback: FeedbackConstraint | None = None,
    ) -> CollectorConfiguration:
        collector_types = task.collector_type
        if isinstance(collector_types, CollectorType):
            collector_types = [collector_types]

        user_prompt = self._build_prompt(task, collector_types, feedback)

        response_schema = {
            "type": "array",
            "items": {"type": "object"},
            "minItems": len(collector_types),
            "maxItems": len(collector_types),
        }

        configs_raw = self.llm.generate_structured(SYSTEM_PROMPT, user_prompt, response_schema)

        collectors = []
        for i, config_data in enumerate(configs_raw):
            ct = collector_types[i] if i < len(collector_types) else collector_types[-1]
            config_data["collector_type"] = ct.value
            collector = self._parse_config(ct, config_data)
            collectors.append(collector)

        return CollectorConfiguration(
            task=task,
            collectors=collectors,
            validation=ValidationThresholds(),
        )

    def _build_prompt(
        self,
        task: TaskRepresentation,
        collector_types: list[CollectorType],
        feedback: FeedbackConstraint | None,
    ) -> str:
        parts = [
            f"## Task\n{task.description}\n",
            f"## Source\n{task.source}\n",
            f"## Required Fields\n{json.dumps([f.model_dump() for f in task.fields], indent=2)}\n",
            f"## Collector Types Required\n{[ct.value for ct in collector_types]}\n",
        ]

        if task.source_context.homepage_title:
            parts.append(f"## Source Context\n")
            if task.source_context.dom_summary:
                parts.append(f"DOM: {task.source_context.dom_summary}\n")
            if task.source_context.candidate_urls:
                parts.append(f"Sample URLs: {task.source_context.candidate_urls[:5]}\n")
            if task.source_context.pagination_clues:
                parts.append(f"Pagination: {task.source_context.pagination_clues}\n")

        if task.constraints:
            parts.append(f"## Constraints\n{task.constraints.model_dump_json(indent=2)}\n")

        if feedback:
            parts.append(self._format_feedback(feedback))

        parts.append(
            f"\nProduce exactly {len(collector_types)} configuration(s) in order: "
            f"{[ct.value for ct in collector_types]}.\n"
            "Each must match its collector type schema exactly."
        )

        return "\n".join(parts)

    def _format_feedback(self, feedback: FeedbackConstraint) -> str:
        parts = [
            "\n## FEEDBACK CONSTRAINT (you MUST follow these)",
            f"Error type: {feedback.error_tag.value}",
            f"Correction hint: {feedback.correction_hint}",
        ]
        if feedback.blacklist:
            parts.append(f"BLACKLIST (do NOT use these): {feedback.blacklist}")
        if feedback.failed_selectors:
            parts.append(f"Failed selectors (do NOT reuse): {feedback.failed_selectors}")
        if feedback.failed_field_paths:
            parts.append(f"Failed field paths (do NOT reuse): {feedback.failed_field_paths}")
        return "\n".join(parts)

    def _parse_config(self, ct: CollectorType, data: dict) -> CollectorConfig:
        data.pop("collector_type", None)

        if ct == CollectorType.SEARCH:
            return SearchConfig(collector_type=ct, **data)
        elif ct == CollectorType.LIST:
            return ListConfig(collector_type=ct, **data)
        elif ct == CollectorType.DETAIL:
            return DetailConfig(collector_type=ct, **data)
        elif ct == CollectorType.API:
            return APIConfig(collector_type=ct, **data)
        elif ct == CollectorType.INTERACTIVE:
            actions = [ActionStep(**a) for a in data.pop("actions", [])]
            return InteractiveConfig(collector_type=ct, actions=actions, **data)
        elif ct == CollectorType.FILE:
            return FileConfig(collector_type=ct, **data)
        raise ValueError(f"Unknown collector type: {ct}")
