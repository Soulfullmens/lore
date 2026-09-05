"""Eval package — harness, stats, and benchmark tooling."""

from .harness import (
    AblationConfig,
    AblationRecord,
    BackendFactory,
    ConditionSummary,
    Harness,
    HarnessReport,
    Mode,
    RunConfig,
    RunRecord,
)
from .stats import Estimate, bootstrap_ci, welch_t

__all__ = [
    "AblationConfig",
    "AblationRecord",
    "BackendFactory",
    "ConditionSummary",
    "Estimate",
    "Harness",
    "HarnessReport",
    "Mode",
    "RunConfig",
    "RunRecord",
    "bootstrap_ci",
    "welch_t",
]
