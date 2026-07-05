"""Requirement Understanding Agent.

Probes the target source, determines collector type, and produces
the full task representation R = (d, s, x, f, c, o).
"""

from __future__ import annotations

from failsafe.agents.llm import LLMClient
from failsafe.schema import (
    CollectionConstraints,
    CollectorType,
    FieldSpec,
    OutputFormat,
    SourceContext,
    TaskRepresentation,
)
from failsafe.utils.request import RequestError, fetch_page, parse_html

SYSTEM_PROMPT = """\
You are a Requirement Understanding Agent for a web data collection framework.

Your job is to analyze a user's collection task description and a probed source context,
then produce a structured task representation.

## Collector Type Taxonomy (choose exactly one or a composition):

1. **search** — Discovers candidate URLs by keyword from search entry points.
   Input: keywords + time range. Output: result links and titles. No content extraction.

2. **list** — Traverses paginated list pages to discover detail-page links.
   Input: column URL + page range. Output: list items and detail links. No deep extraction.

3. **detail** — Extracts structured fields from a single detail page.
   Input: detail-page URL. Output: structured fields (title, body, author, timestamp).

4. **api** — Calls public APIs and maps response fields.
   Input: endpoint URL + request params. Output: structured records. No browser interaction.

5. **interactive** — Executes clicks, text input, page actions on dynamic pages.
   Input: page URL + action sequence. Output: rendered data. No auth/CAPTCHA bypass.

6. **file** — Downloads and parses publicly accessible files (PDF, Excel, CSV).
   Input: file URL. Output: file text and metadata. No semantic judgment.

## Common Compositions:
- search+detail (keyword news collection)
- list+detail+file (announcements with attachments)
- interactive+list+detail (dynamic forms leading to lists)

## Output Requirements:
Produce a JSON object with these fields:
- collector_type: string or array of strings from the taxonomy
- source: the target URL/domain
- fields: array of {name, type, required, description} objects
- constraints: {max_pages, max_records, time_range_days, rate_limit_seconds}
- output_format: {format, flatten, deduplicate}
- confidence: float 0-1 indicating how confident you are in the classification
"""

TASK_SCHEMA = {
    "type": "object",
    "required": ["collector_type", "source", "fields", "constraints", "output_format", "confidence"],
    "properties": {
        "collector_type": {
            "oneOf": [
                {"type": "string", "enum": ["search", "list", "detail", "api", "interactive", "file"]},
                {"type": "array", "items": {"type": "string", "enum": ["search", "list", "detail", "api", "interactive", "file"]}},
            ]
        },
        "source": {"type": "string"},
        "fields": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "type"],
                "properties": {
                    "name": {"type": "string"},
                    "type": {"type": "string"},
                    "required": {"type": "boolean"},
                    "description": {"type": "string"},
                },
            },
        },
        "constraints": {
            "type": "object",
            "properties": {
                "max_pages": {"type": "integer"},
                "max_records": {"type": "integer"},
                "time_range_days": {"type": "integer"},
                "rate_limit_seconds": {"type": "number"},
            },
        },
        "output_format": {
            "type": "object",
            "properties": {
                "format": {"type": "string"},
                "flatten": {"type": "boolean"},
                "deduplicate": {"type": "boolean"},
            },
        },
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
}


class RequirementAgent:
    def __init__(self, llm: LLMClient | None = None):
        self.llm = llm or LLMClient()

    def understand(self, description: str, source_url: str) -> TaskRepresentation:
        source_context = self._probe_source(source_url)
        context_text = self._format_context(source_context)

        user_prompt = (
            f"## Task Description\n{description}\n\n"
            f"## Target Source\n{source_url}\n\n"
            f"## Probed Source Context\n{context_text}\n\n"
            "Analyze this task and produce the structured task representation."
        )

        result = self.llm.generate_structured(SYSTEM_PROMPT, user_prompt, TASK_SCHEMA)

        collector_type = result["collector_type"]
        if isinstance(collector_type, list):
            collector_type = [CollectorType(ct) for ct in collector_type]
        else:
            collector_type = CollectorType(collector_type)

        fields = [
            FieldSpec(
                name=f["name"],
                type=f.get("type", "string"),
                required=f.get("required", True),
                description=f.get("description"),
            )
            for f in result.get("fields", [])
        ]

        constraints_data = result.get("constraints", {})
        constraints = CollectionConstraints(
            max_pages=constraints_data.get("max_pages"),
            max_records=constraints_data.get("max_records"),
            time_range_days=constraints_data.get("time_range_days"),
            rate_limit_seconds=constraints_data.get("rate_limit_seconds", 1.0),
        )

        output_data = result.get("output_format", {})
        output_format = OutputFormat(
            format=output_data.get("format", "json"),
            flatten=output_data.get("flatten", False),
            deduplicate=output_data.get("deduplicate", True),
        )

        return TaskRepresentation(
            description=description,
            source=source_url,
            source_context=source_context,
            fields=fields,
            constraints=constraints,
            output_format=output_format,
            collector_type=collector_type,
            confidence=result.get("confidence", 0.5),
        )

    def _probe_source(self, url: str) -> SourceContext:
        ctx = SourceContext()
        try:
            html = fetch_page(url, rate_limit=0.5)
            soup = parse_html(html)

            title_tag = soup.find("title")
            ctx.homepage_title = title_tag.get_text(strip=True) if title_tag else None

            nav_links = soup.select("nav a, .nav a, .menu a")[:20]
            ctx.column_structures = [a.get_text(strip=True) for a in nav_links if a.get_text(strip=True)]

            main_links = soup.select("main a, .content a, article a")[:10]
            ctx.candidate_urls = [
                a.get("href", "") for a in main_links if a.get("href", "").startswith("http")
            ]

            body = soup.find("body")
            if body:
                tags = [tag.name for tag in body.find_all(recursive=False)][:20]
                ctx.dom_summary = ", ".join(tags)

            pagination = soup.select(".pagination, .pager, [class*=page], nav[aria-label*=page]")
            if pagination:
                ctx.pagination_clues = "Pagination elements detected"

            api_links = soup.select("a[href*=api], a[href*=json], script[src*=api]")
            ctx.has_api = len(api_links) > 0

            file_links = soup.select("a[href$='.pdf'], a[href$='.xlsx'], a[href$='.csv']")
            ctx.has_file_attachments = len(file_links) > 0

        except RequestError:
            pass
        return ctx

    def _format_context(self, ctx: SourceContext) -> str:
        parts = []
        if ctx.homepage_title:
            parts.append(f"Page title: {ctx.homepage_title}")
        if ctx.column_structures:
            parts.append(f"Navigation: {', '.join(ctx.column_structures[:10])}")
        if ctx.candidate_urls:
            parts.append(f"Sample URLs: {', '.join(ctx.candidate_urls[:5])}")
        if ctx.dom_summary:
            parts.append(f"DOM structure: {ctx.dom_summary}")
        if ctx.pagination_clues:
            parts.append(f"Pagination: {ctx.pagination_clues}")
        if ctx.has_api:
            parts.append("API endpoints detected")
        if ctx.has_file_attachments:
            parts.append("File attachments (PDF/Excel) detected")
        return "\n".join(parts) if parts else "No context available (source may be unreachable)"
