"""Verification package — Phase 3 causal credit assignment and confidence engine.

Components:
    Reflector          — counterfactual ablation comparison (4-quadrant attribution)
    CreditAssigner     — Bayesian posterior updates (global + per-model)
    NegativeGuardGenerator — emits guard lessons when positive advice harms
    SequentialAnalyzer  — early stopping via Beta CDF posterior probabilities
    CausalAttribution   — enum of the 4 counterfactual quadrants
    BaselineMissingError — explicit error when baseline cache is absent
"""

from .reflector import Reflector, CausalAttribution, BaselineMissingError, SeedOutcome
from .credit import CreditAssigner, CreditReport
from .guard import NegativeGuardGenerator, GuardReport
from .sequential import SequentialAnalyzer, SequentialDecision

__all__ = [
    "Reflector",
    "SeedOutcome",
    "CausalAttribution",
    "BaselineMissingError",
    "CreditAssigner",
    "CreditReport",
    "NegativeGuardGenerator",
    "GuardReport",
    "SequentialAnalyzer",
    "SequentialDecision",
]
