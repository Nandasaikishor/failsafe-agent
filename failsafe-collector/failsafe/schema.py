"""Core schema definitions for the failsafe collector framework.

Defines the six collector types, task representation R, configuration M,
and quality report structures as typed Pydantic models.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field


class CollectorType(str, Enum):
    SEARCH = "search"
    LIST = "list"
    DETAIL = "detail"
    API = "api"
    INTERACTIVE = "interactive"
    FILE = "file"


class ErrorTag(str, Enum):
    SOURCE_DEFECT = "source_defect"
    PARSE_ERROR = "parse_error"
    SCHEMA_ERROR = "schema_error"
    RUNTIME_ERROR = "runtime_error"
    CONTENT_NOISE = "content_noise"
    LOW_RELEVANCE = "low_relevance"


CORRECTION_PRIORITY = [
    ErrorTag.PARSE_ERROR,
    ErrorTag.SCHEMA_ERROR,
    ErrorTag.RUNTIME_ERROR,
    ErrorTag.CONTENT_NOISE,
    ErrorTag.LOW_RELEVANCE,
]


class FieldSpec(BaseModel):
    name: str
    type: str = "string"
    required: bool = True
    min_length: Optional[int] = None
    description: Optional[str] = None


class CollectionConstraints(BaseModel):
    max_pages: Optional[int] = None
    max_records: Optional[int] = None
    time_range_days: Optional[int] = None
    rate_limit_seconds: float = 1.0
    timeout_seconds: float = 30.0
    respect_robots_txt: bool = True


class OutputFormat(BaseModel):
    format: str = "json"
    flatten: bool = False
    deduplicate: bool = True


class SourceContext(BaseModel):
    homepage_title: Optional[str] = None
    column_structures: List[str] = Field(default_factory=list)
    candidate_urls: List[str] = Field(default_factory=list)
    dom_summary: Optional[str] = None
    pagination_clues: Optional[str] = None
    sample_records: List[Dict[str, Any]] = Field(default_factory=list)
    has_api: bool = False
    requires_interaction: bool = False
    has_file_attachments: bool = False


class TaskRepresentation(BaseModel):
    """Full task representation R = (d, s, x, f, c, o)."""

    description: str = Field(..., description="Initial task description d")
    source: str = Field(..., description="Target source identifier s")
    source_context: SourceContext = Field(
        default_factory=SourceContext, description="Source context from proactive probing x"
    )
    fields: List[FieldSpec] = Field(default_factory=list, description="Required field set f")
    constraints: CollectionConstraints = Field(
        default_factory=CollectionConstraints, description="Collection constraints c"
    )
    output_format: OutputFormat = Field(
        default_factory=OutputFormat, description="Output format o"
    )
    collector_type: Union[CollectorType, List[CollectorType]] = Field(
        ..., description="Collector type or composition kappa"
    )
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


# --- Collector Configuration Schemas ---


class SearchConfig(BaseModel):
    """Configuration for search collector."""

    collector_type: CollectorType = CollectorType.SEARCH
    search_url: str
    keyword_param: str = "q"
    keywords: List[str]
    time_range_param: Optional[str] = None
    result_selector: str
    title_selector: str
    link_selector: str
    next_page_selector: Optional[str] = None
    max_pages: int = 5


class ListConfig(BaseModel):
    """Configuration for list collector."""

    collector_type: CollectorType = CollectorType.LIST
    list_url: str
    item_selector: str
    title_selector: str
    link_selector: str
    date_selector: Optional[str] = None
    next_page_selector: Optional[str] = None
    page_param: Optional[str] = None
    start_page: int = 1
    max_pages: int = 10


class DetailConfig(BaseModel):
    """Configuration for detail collector."""

    collector_type: CollectorType = CollectorType.DETAIL
    url_pattern: Optional[str] = None
    field_selectors: Dict[str, str]
    content_selector: Optional[str] = None
    attachment_selector: Optional[str] = None
    date_format: Optional[str] = None
    encoding: str = "utf-8"


class APIConfig(BaseModel):
    """Configuration for API collector."""

    collector_type: CollectorType = CollectorType.API
    endpoint_url: str
    method: str = "GET"
    headers: Dict[str, str] = Field(default_factory=dict)
    params: Dict[str, Any] = Field(default_factory=dict)
    body: Optional[Dict[str, Any]] = None
    pagination_type: Optional[str] = None
    pagination_param: Optional[str] = None
    data_path: str = "$"
    field_mappings: Dict[str, str] = Field(default_factory=dict)
    max_pages: int = 10


class ActionStep(BaseModel):
    action: str  # click, type, wait, scroll, select
    selector: Optional[str] = None
    value: Optional[str] = None
    wait_ms: int = 1000


class InteractiveConfig(BaseModel):
    """Configuration for interactive collector."""

    collector_type: CollectorType = CollectorType.INTERACTIVE
    url: str
    actions: List[ActionStep]
    result_selector: str
    field_selectors: Dict[str, str]
    wait_for_selector: Optional[str] = None
    screenshot: bool = False


class FileConfig(BaseModel):
    """Configuration for file collector."""

    collector_type: CollectorType = CollectorType.FILE
    file_url: str
    file_type: str  # pdf, xlsx, csv, docx
    sheet_name: Optional[str] = None
    start_row: int = 0
    header_row: Optional[int] = 0
    field_mappings: Dict[str, Union[str, int]] = Field(default_factory=dict)
    encoding: str = "utf-8"


CollectorConfig = Union[SearchConfig, ListConfig, DetailConfig, APIConfig, InteractiveConfig, FileConfig]


class ValidationThresholds(BaseModel):
    min_quality_score: float = 0.60
    structure_weight: float = 0.35
    content_weight: float = 0.25
    relevance_weight: float = 0.20
    attachment_weight: float = 0.10
    execution_weight: float = 0.10
    max_correction_rounds: int = 3


class CollectorConfiguration(BaseModel):
    """Full configuration M = (C, P, V).

    C = collector type/composition
    P = runtime parameters (the config)
    V = validation thresholds
    """

    task: TaskRepresentation
    collectors: List[CollectorConfig]
    validation: ValidationThresholds = Field(default_factory=ValidationThresholds)
    dag_id: Optional[str] = None


# --- Quality Report ---


class DimensionScore(BaseModel):
    structure: float = 0.0
    content: float = 0.0
    relevance: float = 0.0
    attachment: float = 1.0
    execution: float = 0.0


class QualityReport(BaseModel):
    """Quality report Q produced by rule-based assessment."""

    scores: DimensionScore
    composite_score: float = 0.0
    passed: bool = False
    error_tags: List[ErrorTag] = Field(default_factory=list)
    correction_hints: List[str] = Field(default_factory=list)
    execution_metadata: Dict[str, Any] = Field(default_factory=dict)
    sample_data: List[Dict[str, Any]] = Field(default_factory=list)


class FeedbackConstraint(BaseModel):
    """Structured feedback constraint Gamma_t."""

    error_tag: ErrorTag
    failed_selectors: List[str] = Field(default_factory=list)
    failed_field_paths: List[str] = Field(default_factory=list)
    failed_hypotheses: List[str] = Field(default_factory=list)
    correction_hint: str
    blacklist: List[str] = Field(default_factory=list)
