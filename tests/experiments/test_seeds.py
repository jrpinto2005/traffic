"""Per-stream seed derivation invariants (D-017)."""

from __future__ import annotations

from traffic_lab.experiments.seeds import SEED_STREAMS, derive_seeds


def test_derives_one_seed_per_stream() -> None:
    seeds = derive_seeds(0)
    assert set(seeds) == set(SEED_STREAMS)
    assert all(isinstance(v, int) for v in seeds.values())


def test_deterministic_across_calls() -> None:
    """Same master seed, called independently, derives identical per-stream seeds.

    This is what lets the same master seed reproduce the same demand realisation
    (D-017 common random numbers) on any run and any machine.
    """
    assert derive_seeds(42) == derive_seeds(42)


def test_different_master_seeds_diverge() -> None:
    assert derive_seeds(1) != derive_seeds(2)


def test_streams_are_pairwise_independent_values() -> None:
    """Sanity check that spawning did not collapse to one repeated value."""
    seeds = derive_seeds(7)
    assert len(set(seeds.values())) == len(SEED_STREAMS)
