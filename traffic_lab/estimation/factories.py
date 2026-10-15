"""Estimator factories for experiments (M3).

Provides top-level estimator factory functions suitable for multiprocessing worker instantiation.
"""

from __future__ import annotations

from traffic_lab.domain.network import Network
from traffic_lab.estimation.decay import CountingWithDecayEstimator, DecayEstimatorConfig
from traffic_lab.estimation.estimator import Estimator
from traffic_lab.estimation.identity import IdentityEstimator


def make_identity_estimator(network: Network) -> Estimator:
    """Create stateless identity estimator."""
    return IdentityEstimator(network)


def make_decay_estimator(
    network: Network,
    *,
    half_life_s: float = 15.0,
    default_queue_std: float = 1.0,
) -> Estimator:
    """Create counting-with-decay estimator."""
    config = DecayEstimatorConfig(half_life_s=half_life_s, default_queue_std=default_queue_std)
    return CountingWithDecayEstimator(network, config)
