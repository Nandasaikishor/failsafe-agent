"""Rule-based quality scoring — zero LLM tokens.

Implements the five-dimension composite score:
S = w_s*S_s + w_c*S_c + w_r*S_r + w_a*S_a + w_e*S_e

Default weights: (0.35, 0.25, 0.20, 0.10, 0.10)
Pass threshold: S >= 0.60
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from failsafe.collectors.base import CollectionResult
from failsafe.schema import (
    DimensionScore,
    ErrorTag,
    FieldSpec,
    QualityReport,
    ValidationThresholds,
)


class QualityScorer:
    def __init__(self, thresholds: ValidationThresholds | None = None):
        self.thresholds = thresholds or ValidationThresholds()

    def assess(
        self,
        result: CollectionResult,
        expected_fields: list[FieldSpec],
        execution_errors: Optional[List[str]] = None,
    ) -> QualityReport:
        scores = DimensionScore(
            structure=self._score_structure(result.records, expected_fields),
            content=self._score_content(result.records, expected_fields),
            relevance=self._score_relevance(result.records, expected_fields),
            attachment=self._score_attachment(result.records),
            execution=self._score_execution(result, execution_errors),
        )

        composite = (
            self.thresholds.structure_weight * scores.structure
            + self.thresholds.content_weight * scores.content
            + self.thresholds.relevance_weight * scores.relevance
            + self.thresholds.attachment_weight * scores.attachment
            + self.thresholds.execution_weight * scores.execution
        )

        passed = composite >= self.thresholds.min_quality_score
        error_tags = self._detect_errors(result, scores, expected_fields)
        hints = self._generate_hints(error_tags, scores, result)

        return QualityReport(
            scores=scores,
            composite_score=round(composite, 4),
            passed=passed,
            error_tags=error_tags,
            correction_hints=hints,
            execution_metadata=result.metadata,
            sample_data=result.records[:5],
        )

    def _score_structure(
        self, records: list[dict[str, Any]], expected_fields: list[FieldSpec]
    ) -> float:
        """S_s: Ratio of valid to expected fields."""
        if not expected_fields or not records:
            return 0.0

        expected_names = {f.name for f in expected_fields}
        total_expected = len(expected_names)

        if total_expected == 0:
            return 1.0

        field_present_counts = {name: 0 for name in expected_names}
        for record in records:
            for name in expected_names:
                if name in record:
                    field_present_counts[name] += 1

        fields_present = sum(1 for count in field_present_counts.values() if count > 0)
        return fields_present / total_expected

    def _score_content(
        self, records: list[dict[str, Any]], expected_fields: list[FieldSpec]
    ) -> float:
        """S_c: Fraction of non-empty values exceeding per-field thresholds."""
        if not records or not expected_fields:
            return 0.0

        expected_names = [f.name for f in expected_fields]
        if not expected_names:
            return 1.0

        non_empty_fields = 0
        total_fields = 0

        for name in expected_names:
            total_fields += 1
            non_empty_count = 0
            for record in records:
                value = record.get(name)
                if value is not None and str(value).strip():
                    non_empty_count += 1
            if non_empty_count > 0:
                non_empty_fields += 1

        return non_empty_fields / total_fields if total_fields > 0 else 0.0

    def _score_relevance(
        self, records: list[dict[str, Any]], expected_fields: list[FieldSpec]
    ) -> float:
        """S_r: Mean keyword-overlap similarity to target schema."""
        if not records or not expected_fields:
            return 0.0

        target_keywords = set()
        for f in expected_fields:
            target_keywords.add(f.name.lower())
            if f.description:
                target_keywords.update(f.description.lower().split())

        if not target_keywords:
            return 1.0

        record_keywords = set()
        for record in records:
            for key in record.keys():
                record_keywords.add(key.lower())

        overlap = target_keywords & record_keywords
        return len(overlap) / len(target_keywords) if target_keywords else 0.0

    def _score_attachment(self, records: list[dict[str, Any]]) -> float:
        """S_a: Ratio of valid to expected attachments. Default 1.0 if none expected."""
        has_attachments = any("attachments" in r for r in records)
        if not has_attachments:
            return 1.0

        total = 0
        valid = 0
        for record in records:
            attachments = record.get("attachments", [])
            if isinstance(attachments, list):
                for att in attachments:
                    total += 1
                    if att and str(att).startswith(("http://", "https://")):
                        valid += 1

        return valid / total if total > 0 else 1.0

    def _score_execution(
        self, result: CollectionResult, execution_errors: Optional[List[str]]
    ) -> float:
        """S_e: No errors = 1.0, partial = 0.5, total failure = 0.0."""
        all_errors = result.errors + (execution_errors or [])
        if not all_errors:
            return 1.0
        if result.records:
            return 0.5
        return 0.0

    def _detect_errors(
        self,
        result: CollectionResult,
        scores: DimensionScore,
        expected_fields: list[FieldSpec],
    ) -> list[ErrorTag]:
        errors = []

        if not result.records and result.errors:
            if any("HTTP" in e for e in result.errors):
                errors.append(ErrorTag.SOURCE_DEFECT)
            else:
                errors.append(ErrorTag.RUNTIME_ERROR)

        if scores.structure < 0.5 and result.records:
            errors.append(ErrorTag.SCHEMA_ERROR)

        if scores.content < 0.5 and result.records:
            errors.append(ErrorTag.PARSE_ERROR)

        if scores.relevance < 0.3:
            errors.append(ErrorTag.LOW_RELEVANCE)

        if scores.content > 0.5 and scores.relevance < 0.5:
            errors.append(ErrorTag.CONTENT_NOISE)

        return errors

    def _generate_hints(
        self,
        errors: list[ErrorTag],
        scores: DimensionScore,
        result: CollectionResult,
    ) -> list[str]:
        hints = []

        if ErrorTag.PARSE_ERROR in errors:
            hints.append(
                "Content extraction is failing — selectors may not match the actual DOM. "
                "Check field_selectors against the page structure."
            )

        if ErrorTag.SCHEMA_ERROR in errors:
            hints.append(
                "Expected fields are missing from results. Verify that field names in "
                "field_selectors match the expected output schema."
            )

        if ErrorTag.RUNTIME_ERROR in errors:
            if result.errors:
                hints.append(f"Runtime errors: {'; '.join(result.errors[:3])}")

        if ErrorTag.SOURCE_DEFECT in errors:
            hints.append(
                "Source may be unreachable or returning errors. "
                "Verify the URL is correct and publicly accessible."
            )

        if ErrorTag.LOW_RELEVANCE in errors:
            hints.append(
                "Collected data does not match expected fields. "
                "Review field_mappings or data_path configuration."
            )

        if ErrorTag.CONTENT_NOISE in errors:
            hints.append(
                "Data contains noise — selectors may be too broad. "
                "Use more specific selectors to target relevant content."
            )

        return hints
