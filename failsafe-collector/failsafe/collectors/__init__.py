"""Collector operators — deterministic execution with zero LLM tokens."""

from failsafe.collectors.search import SearchCollector
from failsafe.collectors.list import ListCollector
from failsafe.collectors.detail import DetailCollector
from failsafe.collectors.api import APICollector
from failsafe.collectors.interactive import InteractiveCollector
from failsafe.collectors.file import FileCollector
from failsafe.schema import CollectorType

COLLECTOR_REGISTRY = {
    CollectorType.SEARCH: SearchCollector,
    CollectorType.LIST: ListCollector,
    CollectorType.DETAIL: DetailCollector,
    CollectorType.API: APICollector,
    CollectorType.INTERACTIVE: InteractiveCollector,
    CollectorType.FILE: FileCollector,
}


def get_collector(collector_type: CollectorType):
    return COLLECTOR_REGISTRY[collector_type]
