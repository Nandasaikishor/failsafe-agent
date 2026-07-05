"""Main orchestrator — implements the full closed loop.

Flow: generate -> validate -> assess -> constrain -> regenerate

This module can be used standalone (without Airflow) for development/testing,
or the Airflow DAG can be triggered with the configuration it produces.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from failsafe.collectors import get_collector
from failsafe.collectors.base import CollectionResult
from failsafe.feedback.correction import CorrectionState, FeedbackCorrector
from failsafe.quality.scorer import QualityScorer
from failsafe.schema import (
    CollectorConfiguration,
    CollectorType,
    FeedbackConstraint,
    QualityReport,
    TaskRepresentation,
    ValidationThresholds,
)

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    task: TaskRepresentation
    configuration: CollectorConfiguration
    quality_report: QualityReport
    records: list[dict[str, Any]] = field(default_factory=list)
    correction_rounds: int = 0
    passed: bool = False


class FailsafeOrchestrator:
    """End-to-end orchestrator for the failsafe collection framework.

    Standalone execution path (no Airflow required):
    1. Requirement Understanding Agent -> TaskRepresentation
    2. Collector Instantiation Agent -> CollectorConfiguration
    3. Validation execution (small-sample)
    4. Quality assessment
    5. Feedback correction loop (if needed)
    6. Scale execution (if passed)
    """

    def __init__(
        self,
        api_key: str = None,
        model: str = "claude-sonnet-4-20250514",
        max_correction_rounds: int = 3,
        output_dir: str = "/tmp/failsafe_output",
    ):
        self._api_key = api_key
        self._model = model
        self._llm = None
        self._requirement_agent = None
        self._instantiation_agent = None
        self.quality_scorer = QualityScorer()
        self.feedback_corrector = FeedbackCorrector(max_rounds=max_correction_rounds)
        self.max_correction_rounds = max_correction_rounds
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    @property
    def llm(self):
        if self._llm is None:
            from failsafe.agents.llm import LLMClient
            self._llm = LLMClient(api_key=self._api_key, model=self._model)
        return self._llm

    @property
    def requirement_agent(self):
        if self._requirement_agent is None:
            from failsafe.agents.requirement import RequirementAgent
            self._requirement_agent = RequirementAgent(self.llm)
        return self._requirement_agent

    @property
    def instantiation_agent(self):
        if self._instantiation_agent is None:
            from failsafe.agents.instantiation import InstantiationAgent
            self._instantiation_agent = InstantiationAgent(self.llm)
        return self._instantiation_agent

    def run(
        self,
        description: str,
        source_url: str,
        *,
        validation_only: bool = False,
    ) -> PipelineResult:
        """Execute the full pipeline."""
        logger.info("Step 1: Understanding requirements")
        task = self.requirement_agent.understand(description, source_url)
        logger.info(
            f"  Collector type: {task.collector_type}, "
            f"Fields: {[f.name for f in task.fields]}, "
            f"Confidence: {task.confidence:.2f}"
        )

        logger.info("Step 2: Instantiating collector configuration")
        config = self.instantiation_agent.instantiate(task)

        logger.info("Step 3: Validation execution (small-sample)")
        result = self._execute_validation(config)

        logger.info("Step 4: Quality assessment")
        report = self.quality_scorer.assess(result, task.fields)
        logger.info(
            f"  Score: {report.composite_score:.4f}, "
            f"Passed: {report.passed}, "
            f"Errors: {[e.value for e in report.error_tags]}"
        )

        correction_rounds = 0
        state = CorrectionState()

        while not report.passed and correction_rounds < self.max_correction_rounds:
            logger.info(f"Step 5: Feedback correction (round {correction_rounds + 1})")
            feedback = self.feedback_corrector.compute_feedback(config, report, state)

            if feedback is None:
                logger.warning("  No viable correction — stopping")
                break

            logger.info(f"  Applying constraint: {feedback.error_tag.value}")
            config = self.instantiation_agent.instantiate(task, feedback=feedback)

            result = self._execute_validation(config)
            report = self.quality_scorer.assess(result, task.fields)
            correction_rounds += 1

            logger.info(
                f"  Round {correction_rounds} score: {report.composite_score:.4f}, "
                f"Passed: {report.passed}"
            )

        if report.passed and not validation_only:
            logger.info("Step 6: Scale execution")
            result = self._execute_scale(config)
            report = self.quality_scorer.assess(result, task.fields)

        pipeline_result = PipelineResult(
            task=task,
            configuration=config,
            quality_report=report,
            records=result.records,
            correction_rounds=correction_rounds,
            passed=report.passed,
        )

        self._persist(pipeline_result)
        return pipeline_result

    def run_from_config(
        self,
        config_path: str | Path,
        *,
        validation_only: bool = False,
    ) -> PipelineResult:
        """Execute from an existing configuration file (no LLM calls)."""
        with open(config_path) as f:
            config_dict = json.load(f)

        config = CollectorConfiguration.model_validate(config_dict)
        task = config.task

        result = self._execute_validation(config)
        report = self.quality_scorer.assess(result, task.fields)

        if report.passed and not validation_only:
            result = self._execute_scale(config)
            report = self.quality_scorer.assess(result, task.fields)

        pipeline_result = PipelineResult(
            task=task,
            configuration=config,
            quality_report=report,
            records=result.records,
            correction_rounds=0,
            passed=report.passed,
        )
        self._persist(pipeline_result)
        return pipeline_result

    def _execute_validation(self, config: CollectorConfiguration) -> CollectionResult:
        """Small-sample validation run."""
        return self._execute(config, max_pages=2, max_records=10)

    def _execute_scale(self, config: CollectorConfiguration) -> CollectionResult:
        """Full-scale production run."""
        return self._execute(config, max_pages=None, max_records=None)

    def _execute(
        self,
        config: CollectorConfiguration,
        max_pages: int | None,
        max_records: int | None,
    ) -> CollectionResult:
        """Execute collectors deterministically."""
        all_results = []
        discovered_urls: list[str] = []

        for collector_config in config.collectors:
            collector_cls = get_collector(collector_config.collector_type)
            collector = collector_cls()

            kwargs: dict[str, Any] = {
                "rate_limit": config.task.constraints.rate_limit_seconds,
            }
            if discovered_urls:
                kwargs["urls"] = discovered_urls

            if max_pages and hasattr(collector_config, "max_pages"):
                original = collector_config.max_pages
                collector_config.max_pages = min(max_pages, original)

            result = collector.execute(collector_config, **kwargs)
            all_results.append(result)

            if result.urls_discovered:
                discovered_urls = result.urls_discovered
                if max_records:
                    discovered_urls = discovered_urls[:max_records]

        combined = CollectionResult(
            records=[r for res in all_results for r in res.records],
            urls_discovered=[u for res in all_results for u in res.urls_discovered],
            errors=[e for res in all_results for e in res.errors],
            metadata={"collectors_run": len(all_results)},
        )

        if max_records:
            combined.records = combined.records[:max_records]

        return combined

    def _persist(self, result: PipelineResult) -> None:
        """Persist configuration and results."""
        config_path = self.output_dir / "config.json"
        with open(config_path, "w") as f:
            json.dump(result.configuration.model_dump(), f, indent=2, default=str)

        results_path = self.output_dir / "results.json"
        with open(results_path, "w") as f:
            json.dump(result.records, f, indent=2, default=str)

        report_path = self.output_dir / "quality_report.json"
        with open(report_path, "w") as f:
            json.dump(result.quality_report.model_dump(), f, indent=2, default=str)

        logger.info(f"  Output saved to {self.output_dir}")

    def export_airflow_config(self, config: CollectorConfiguration) -> str:
        """Export configuration for Airflow DAG trigger."""
        return json.dumps({"config": config.model_dump()}, indent=2, default=str)
