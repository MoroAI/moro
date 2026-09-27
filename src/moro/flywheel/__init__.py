"""
MoroAI Continuous Learning DPO Flywheel Package.
"""

from moro.flywheel.architecture import (
    AbstractDeploymentGate,
    AbstractDPOTrainerBridge,
    AbstractLogIngestor,
    AbstractPreferenceExtractor,
    AbstractSyntheticGenerator,
)
from moro.flywheel.extractors.deterministic_extractor import DeterministicPreferenceExtractor
from moro.flywheel.generators.grounded_generator import (
    DeterministicGroundedGenerator,
    OllamaGroundedGenerator,
)
from moro.flywheel.ingestors.sqlite_ingestor import SQLiteLogIngestor
from moro.flywheel.models import (
    FeedbackEntry,
    FeedbackType,
    InferenceLogPayload,
    PreferencePair,
    RefinedTrainingPair,
)
from moro.flywheel.orchestrator import (
    DPOExecutionSummary,
    FlywheelConfig,
    MoroAIFlywheelOrchestrator,
)

__all__ = [
    "FeedbackType",
    "InferenceLogPayload",
    "PreferencePair",
    "FeedbackEntry",
    "RefinedTrainingPair",
    "AbstractLogIngestor",
    "AbstractPreferenceExtractor",
    "AbstractSyntheticGenerator",
    "AbstractDPOTrainerBridge",
    "AbstractDeploymentGate",
    "SQLiteLogIngestor",
    "DeterministicPreferenceExtractor",
    "OllamaGroundedGenerator",
    "DeterministicGroundedGenerator",
    "FlywheelConfig",
    "DPOExecutionSummary",
    "MoroAIFlywheelOrchestrator",
]
