"""State-machine-based feedback correction (Algorithm 1 from paper).

Implements the closed loop: generate-validate-assess-constrain-regenerate.

Priority order: parse_error < schema_error < runtime_error < content_noise < low_relevance
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from failsafe.schema import (
    CORRECTION_PRIORITY,
    CollectorConfig,
    CollectorConfiguration,
    ErrorTag,
    FeedbackConstraint,
    QualityReport,
)


@dataclass
class CorrectionState:
    round: int = 0
    blacklist: list[str] = field(default_factory=list)
    history: list[QualityReport] = field(default_factory=list)


class FeedbackCorrector:
    """Implements Algorithm 1: State-Machine-Based Feedback Correction.

    Input: Failed config M_t, quality report Q_t, candidate corrections H_t, blacklist B_t
    Output: Feedback constraint Gamma_t or human-review flag
    """

    def __init__(self, max_rounds: int = 3):
        self.max_rounds = max_rounds

    def compute_feedback(
        self,
        config: CollectorConfiguration,
        report: QualityReport,
        state: CorrectionState,
    ) -> FeedbackConstraint | None:
        """Algorithm 1 implementation.

        Returns None if no correction needed or human review required.
        """
        # Line 1: E_t <- phi(Q_t)
        error_tags = report.error_tags

        # Line 2-4: if E_t = empty, no correction needed
        if not error_tags:
            return None

        if state.round >= self.max_rounds:
            return None

        # Line 5: e* <- SelectByPriority(E_t)
        priority_error = self._select_by_priority(error_tags)

        # Line 6: B_{t+1} <- B_t union FailedHypotheses(M_t, Q_t)
        new_blacklist_items = self._extract_failed_hypotheses(config, report)
        state.blacklist.extend(new_blacklist_items)

        # Line 7: H' <- {h in H_t | h not in B_{t+1}}
        candidates = self._generate_candidates(config, priority_error, report)
        valid_candidates = [h for h in candidates if h not in state.blacklist]

        # Line 8-10: if H' = empty, requires human review
        if not valid_candidates:
            return None

        # Line 11: h_t <- SelectRepairHypothesis(e*, H')
        hypothesis = self._select_repair_hypothesis(priority_error, valid_candidates)

        # Line 12: Gamma_t <- BuildFeedbackConstraint(Q_t, h_t, B_{t+1})
        constraint = self._build_feedback_constraint(
            report, hypothesis, priority_error, state.blacklist
        )

        state.round += 1
        state.history.append(report)

        return constraint

    def _select_by_priority(self, error_tags: list[ErrorTag]) -> ErrorTag:
        """Select highest-priority error tag."""
        for priority_tag in CORRECTION_PRIORITY:
            if priority_tag in error_tags:
                return priority_tag
        return error_tags[0]

    def _extract_failed_hypotheses(
        self, config: CollectorConfiguration, report: QualityReport
    ) -> list[str]:
        """Extract proven-failed selectors, field paths, and hypotheses."""
        failed = []

        for collector in config.collectors:
            collector_dict = collector.model_dump()

            if hasattr(collector, "field_selectors"):
                for field_name, selector in collector_dict.get("field_selectors", {}).items():
                    is_empty = all(
                        not record.get(field_name) for record in report.sample_data
                    )
                    if is_empty and report.sample_data:
                        failed.append(selector)

            if hasattr(collector, "item_selector"):
                if not report.sample_data:
                    failed.append(collector_dict.get("item_selector", ""))

            if hasattr(collector, "result_selector"):
                if not report.sample_data:
                    failed.append(collector_dict.get("result_selector", ""))

        return [f for f in failed if f]

    def _generate_candidates(
        self,
        config: CollectorConfiguration,
        error: ErrorTag,
        report: QualityReport,
    ) -> list[str]:
        """Generate candidate correction hypotheses based on error type."""
        candidates = []

        if error == ErrorTag.PARSE_ERROR:
            candidates.extend([
                "broaden_selectors",
                "try_alternative_selectors",
                "check_iframe_content",
                "handle_dynamic_loading",
            ])
        elif error == ErrorTag.SCHEMA_ERROR:
            candidates.extend([
                "remap_field_names",
                "add_missing_field_selectors",
                "fix_data_path",
            ])
        elif error == ErrorTag.RUNTIME_ERROR:
            candidates.extend([
                "fix_url",
                "adjust_timeout",
                "handle_redirect",
                "fix_encoding",
            ])
        elif error == ErrorTag.CONTENT_NOISE:
            candidates.extend([
                "narrow_selectors",
                "add_content_filter",
                "exclude_navigation",
            ])
        elif error == ErrorTag.LOW_RELEVANCE:
            candidates.extend([
                "adjust_field_mappings",
                "change_data_path",
                "verify_endpoint",
            ])
        elif error == ErrorTag.SOURCE_DEFECT:
            candidates.extend([
                "try_alternative_url",
                "check_robots_txt",
                "add_headers",
            ])

        return candidates

    def _select_repair_hypothesis(
        self, error: ErrorTag, candidates: list[str]
    ) -> str:
        """Select the most promising repair hypothesis."""
        return candidates[0] if candidates else "unknown"

    def _build_feedback_constraint(
        self,
        report: QualityReport,
        hypothesis: str,
        error: ErrorTag,
        blacklist: list[str],
    ) -> FeedbackConstraint:
        """Build structured feedback constraint Gamma_t."""
        failed_selectors = []
        failed_paths = []

        for hint in report.correction_hints:
            if "selector" in hint.lower():
                failed_selectors.append(hint)
            if "path" in hint.lower() or "mapping" in hint.lower():
                failed_paths.append(hint)

        correction_hint = self._hypothesis_to_hint(hypothesis, error, report)

        return FeedbackConstraint(
            error_tag=error,
            failed_selectors=failed_selectors,
            failed_field_paths=failed_paths,
            failed_hypotheses=[hypothesis],
            correction_hint=correction_hint,
            blacklist=blacklist,
        )

    def _hypothesis_to_hint(
        self, hypothesis: str, error: ErrorTag, report: QualityReport
    ) -> str:
        """Convert a repair hypothesis into an actionable constraint hint."""
        base_hints = {
            "broaden_selectors": (
                "Current selectors are too narrow and not matching elements. "
                "Use broader CSS selectors (prefer class-based over structural)."
            ),
            "try_alternative_selectors": (
                "Try different CSS selectors. Look for data-* attributes, "
                "ARIA labels, or semantic HTML elements."
            ),
            "narrow_selectors": (
                "Current selectors are too broad, capturing irrelevant content. "
                "Add more specific class or attribute qualifiers."
            ),
            "remap_field_names": (
                "Field names in output don't match expected schema. "
                "Adjust field_mappings to align source fields to target names."
            ),
            "add_missing_field_selectors": (
                "Some expected fields have no selector. Add selectors for all "
                "required fields in the output schema."
            ),
            "fix_url": (
                "The target URL may be incorrect or have changed. "
                "Verify the URL is publicly accessible and returns expected content."
            ),
            "fix_data_path": (
                "The JSON data path doesn't reach the expected data. "
                "Inspect the API response structure and adjust data_path."
            ),
            "adjust_field_mappings": (
                "Field mappings don't produce relevant output. "
                "Re-examine the source data structure and remap fields."
            ),
            "change_data_path": (
                "The data_path is pointing to wrong location in the response. "
                "Try alternative paths in the JSON response."
            ),
        }

        hint = base_hints.get(hypothesis, f"Apply correction strategy: {hypothesis}")

        if report.correction_hints:
            hint += f" Context: {report.correction_hints[0]}"

        return hint
