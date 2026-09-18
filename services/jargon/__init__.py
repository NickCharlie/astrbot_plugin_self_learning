"""Jargon detection, mining, and query services."""

from .jargon_miner import JargonMiner, JargonMinerManager
from .jargon_query import JargonQueryService
from .jargon_statistical_filter import JargonStatisticalFilter
from .web_search_definition import (
    JargonWebDefinitionService,
    WebSearchClient,
    build_web_definition_service,
)

__all__ = [
    "JargonMiner",
    "JargonMinerManager",
    "JargonQueryService",
    "JargonStatisticalFilter",
    "JargonWebDefinitionService",
    "WebSearchClient",
    "build_web_definition_service",
]
