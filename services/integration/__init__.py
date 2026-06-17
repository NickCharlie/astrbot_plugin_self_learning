"""External integrations -- MaiBot, knowledge graphs, memory engines.

The integration package contains optional-heavy adapters.  Keep package import
lightweight and load concrete classes on demand so tests and WebUI startup can
import a single integration module without initializing every companion engine.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any


_EXPORTS = {
    "MaiBotIntegrationFactory": ".maibot_integration_factory",
    "MaiBotStyleAnalyzer": ".maibot_adapters",
    "MaiBotLearningStrategy": ".maibot_adapters",
    "MaiBotQualityMonitor": ".maibot_adapters",
    "MaiBotEnhancedLearningManager": ".maibot_enhanced_learning_manager",
    "MaiBotLearningImporter": ".maibot_learning_importer",
    "WorldBookImporter": ".worldbook_importer",
    "ExemplarLibrary": ".exemplar_library",
    "KnowledgeGraphManager": ".knowledge_graph_manager",
    "LightRAGKnowledgeManager": ".lightrag_knowledge_manager",
    "Mem0MemoryManager": ".mem0_memory_manager",
    "TrainingDataExporter": ".training_data_exporter",
}

__all__ = list(_EXPORTS)


def __getattr__(name: str) -> Any:
    module_name = _EXPORTS.get(name)
    if not module_name:
        raise AttributeError(name)
    module = import_module(module_name, __name__)
    value = getattr(module, name)
    globals()[name] = value
    return value
