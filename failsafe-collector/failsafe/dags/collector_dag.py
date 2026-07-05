"""Static Airflow DAG for collector execution.

This DAG reads JSON configurations and invokes pre-built utility functions.
Zero LLM tokens at execution time — all intelligence is baked into the config.

The same DAG handles both validation (small-sample) and scale runs,
differing only in trigger parameters.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta

from airflow import DAG
from airflow.models import Variable
from airflow.operators.python import PythonOperator

DEFAULT_ARGS = {
    "owner": "failsafe",
    "depends_on_past": False,
    "email_on_failure": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}


def load_configuration(**context):
    """Load and validate the collector configuration from trigger params or Variable."""
    dag_run = context["dag_run"]
    config_json = dag_run.conf.get("config") if dag_run.conf else None

    if not config_json:
        config_path = Variable.get("failsafe_config_path", default_var=None)
        if config_path and os.path.exists(config_path):
            with open(config_path) as f:
                config_json = json.load(f)
        else:
            raise ValueError("No configuration provided via trigger or Variable")

    if isinstance(config_json, str):
        config_json = json.loads(config_json)

    from failsafe.schema import CollectorConfiguration

    config = CollectorConfiguration.model_validate(config_json)
    context["ti"].xcom_push(key="config", value=config.model_dump())
    return config.model_dump()


def execute_collectors(**context):
    """Generic collector operator — reads config and invokes pre-built utilities."""
    from failsafe.collectors import get_collector
    from failsafe.collectors.base import CollectionResult
    from failsafe.schema import CollectorConfiguration, CollectorType

    config_dict = context["ti"].xcom_pull(task_ids="load_config", key="config")
    config = CollectorConfiguration.model_validate(config_dict)

    dag_run = context["dag_run"]
    is_validation = dag_run.conf.get("validation_mode", True) if dag_run.conf else True
    max_pages_override = 2 if is_validation else None

    all_results = []
    discovered_urls = []

    for collector_config in config.collectors:
        collector_cls = get_collector(collector_config.collector_type)
        collector = collector_cls()

        kwargs = {
            "rate_limit": config.task.constraints.rate_limit_seconds,
        }
        if discovered_urls:
            kwargs["urls"] = discovered_urls

        if max_pages_override and hasattr(collector_config, "max_pages"):
            original_max = collector_config.max_pages
            collector_config.max_pages = min(max_pages_override, original_max)

        result = collector.execute(collector_config, **kwargs)
        all_results.append(result)

        if result.urls_discovered:
            discovered_urls = result.urls_discovered

    combined = CollectionResult(
        records=[r for res in all_results for r in res.records],
        urls_discovered=[u for res in all_results for u in res.urls_discovered],
        errors=[e for res in all_results for e in res.errors],
        metadata={"collectors_run": len(all_results), "validation_mode": is_validation},
    )

    context["ti"].xcom_push(key="results", value={
        "records": combined.records[:1000],
        "urls_discovered": combined.urls_discovered[:100],
        "errors": combined.errors,
        "metadata": combined.metadata,
    })


def assess_quality(**context):
    """Rule-based quality assessment — no LLM tokens."""
    from failsafe.collectors.base import CollectionResult
    from failsafe.quality.scorer import QualityScorer
    from failsafe.schema import CollectorConfiguration, FieldSpec

    config_dict = context["ti"].xcom_pull(task_ids="load_config", key="config")
    config = CollectorConfiguration.model_validate(config_dict)

    results_dict = context["ti"].xcom_pull(task_ids="execute_collectors", key="results")
    result = CollectionResult(
        records=results_dict["records"],
        urls_discovered=results_dict["urls_discovered"],
        errors=results_dict["errors"],
        metadata=results_dict["metadata"],
    )

    scorer = QualityScorer(config.validation)
    report = scorer.assess(result, config.task.fields)

    context["ti"].xcom_push(key="quality_report", value=report.model_dump())
    return report.model_dump()


def persist_results(**context):
    """Persist collected data and quality report."""
    results_dict = context["ti"].xcom_pull(task_ids="execute_collectors", key="results")
    report_dict = context["ti"].xcom_pull(task_ids="assess_quality", key="quality_report")

    output_dir = Variable.get("failsafe_output_dir", default_var="/tmp/failsafe_output")
    os.makedirs(output_dir, exist_ok=True)

    dag_run = context["dag_run"]
    run_id = dag_run.run_id if dag_run else "manual"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    results_path = os.path.join(output_dir, f"results_{timestamp}_{run_id}.json")
    with open(results_path, "w") as f:
        json.dump(results_dict, f, indent=2, default=str)

    report_path = os.path.join(output_dir, f"quality_{timestamp}_{run_id}.json")
    with open(report_path, "w") as f:
        json.dump(report_dict, f, indent=2, default=str)

    context["ti"].xcom_push(key="output_paths", value={
        "results": results_path,
        "report": report_path,
    })


with DAG(
    dag_id="failsafe_collector",
    default_args=DEFAULT_ARGS,
    description="Static collector DAG — zero LLM tokens at execution time",
    schedule=None,
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["failsafe", "collector"],
) as dag:

    load_config = PythonOperator(
        task_id="load_config",
        python_callable=load_configuration,
    )

    execute = PythonOperator(
        task_id="execute_collectors",
        python_callable=execute_collectors,
    )

    quality = PythonOperator(
        task_id="assess_quality",
        python_callable=assess_quality,
    )

    persist = PythonOperator(
        task_id="persist_results",
        python_callable=persist_results,
    )

    load_config >> execute >> quality >> persist
