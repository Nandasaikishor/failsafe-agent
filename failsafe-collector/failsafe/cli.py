"""CLI entry point for the failsafe collector framework."""

from __future__ import annotations

import argparse
import json
import logging
import sys


def main():
    parser = argparse.ArgumentParser(
        description="Failsafe Collector — Constrained, verifiable web data collection"
    )
    parser.add_argument("--api-key", help="Anthropic API key (or set ANTHROPIC_API_KEY env var)")
    subparsers = parser.add_subparsers(dest="command")

    # Run command — full pipeline with LLM
    run_parser = subparsers.add_parser("run", help="Run a collection task end-to-end (requires API key)")
    run_parser.add_argument("description", help="Task description in natural language")
    run_parser.add_argument("source_url", help="Target source URL")
    run_parser.add_argument("--model", default="claude-sonnet-4-20250514", help="Claude model to use")
    run_parser.add_argument("--output-dir", default="/tmp/failsafe_output", help="Output directory")
    run_parser.add_argument("--max-rounds", type=int, default=3, help="Max correction rounds")
    run_parser.add_argument("--validation-only", action="store_true", help="Only run validation")
    run_parser.add_argument("-v", "--verbose", action="store_true")

    # Execute command — from existing config, NO LLM needed
    exec_parser = subparsers.add_parser("execute", help="Execute from existing config (NO API key needed)")
    exec_parser.add_argument("config_path", help="Path to configuration JSON")
    exec_parser.add_argument("--output-dir", default="/tmp/failsafe_output")
    exec_parser.add_argument("--validation-only", action="store_true")
    exec_parser.add_argument("-v", "--verbose", action="store_true")

    # Understand command — requirement analysis only
    understand_parser = subparsers.add_parser("understand", help="Analyze requirements only (requires API key)")
    understand_parser.add_argument("description", help="Task description")
    understand_parser.add_argument("source_url", help="Target source URL")
    understand_parser.add_argument("--model", default="claude-sonnet-4-20250514")
    understand_parser.add_argument("-v", "--verbose", action="store_true")

    # Quality command — assess existing results, NO LLM needed
    quality_parser = subparsers.add_parser("quality", help="Assess quality of existing results (NO API key needed)")
    quality_parser.add_argument("results_path", help="Path to results JSON")
    quality_parser.add_argument("config_path", help="Path to configuration JSON")
    quality_parser.add_argument("-v", "--verbose", action="store_true")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    log_level = logging.DEBUG if getattr(args, "verbose", False) else logging.INFO
    logging.basicConfig(level=log_level, format="%(levelname)s: %(message)s")

    if args.command == "run":
        from failsafe.orchestrator import FailsafeOrchestrator

        orchestrator = FailsafeOrchestrator(
            api_key=args.api_key,
            model=args.model,
            max_correction_rounds=args.max_rounds,
            output_dir=args.output_dir,
        )
        result = orchestrator.run(
            args.description, args.source_url, validation_only=args.validation_only
        )
        print(f"\nResult: {'PASSED' if result.passed else 'FAILED'}")
        print(f"Quality score: {result.quality_report.composite_score:.4f}")
        print(f"Records collected: {len(result.records)}")
        print(f"Correction rounds: {result.correction_rounds}")
        print(f"Output: {args.output_dir}/")

    elif args.command == "execute":
        from failsafe.orchestrator import FailsafeOrchestrator

        orchestrator = FailsafeOrchestrator(output_dir=args.output_dir)
        result = orchestrator.run_from_config(
            args.config_path, validation_only=args.validation_only
        )
        print(f"\nResult: {'PASSED' if result.passed else 'FAILED'}")
        print(f"Quality score: {result.quality_report.composite_score:.4f}")
        print(f"Records collected: {len(result.records)}")
        print(f"Output: {args.output_dir}/")

    elif args.command == "understand":
        from failsafe.agents.llm import LLMClient
        from failsafe.agents.requirement import RequirementAgent

        llm = LLMClient(api_key=args.api_key, model=args.model)
        agent = RequirementAgent(llm)
        task = agent.understand(args.description, args.source_url)
        print(json.dumps(task.model_dump(), indent=2, default=str))

    elif args.command == "quality":
        from failsafe.collectors.base import CollectionResult
        from failsafe.quality.scorer import QualityScorer
        from failsafe.schema import CollectorConfiguration

        with open(args.results_path) as f:
            records = json.load(f)
        with open(args.config_path) as f:
            config = CollectorConfiguration.model_validate(json.load(f))

        result = CollectionResult(records=records if isinstance(records, list) else records.get("records", []))
        scorer = QualityScorer(config.validation)
        report = scorer.assess(result, config.task.fields)
        print(json.dumps(report.model_dump(), indent=2, default=str))


if __name__ == "__main__":
    main()
