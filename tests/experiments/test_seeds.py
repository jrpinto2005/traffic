"""Per-stream seed derivation invariants (D-017)."""

from __future__ import annotations

import inspect

import numpy as np
import pytest

from traffic_lab.experiments.seeds import SEED_MAX, SEED_STREAMS, derive_run_seeds, derive_seeds


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


# --- derive_run_seeds (T1.11) ----------------------------------------------------


def test_run_seeds_cover_every_stream_within_sumos_range() -> None:
    for seed_index in range(200):
        seeds = derive_run_seeds(42, seed_index)
        assert set(seeds) == set(SEED_STREAMS)
        assert all(0 <= v <= SEED_MAX for v in seeds.values())
    assert SEED_MAX == 2147483647  # the largest `--seed` SUMO 1.27.1 parses


def test_run_seeds_are_deterministic() -> None:
    assert derive_run_seeds(42, 3) == derive_run_seeds(42, 3)


def test_run_seeds_follow_the_documented_scheme() -> None:
    """The run is the `seed_index`-th spawned child of the master; the streams are
    that run's children, in `SEED_STREAMS` order, cut to 31 bits."""
    run = np.random.SeedSequence(7).spawn(4)[3]
    expected = {
        stream: int(child.generate_state(1)[0]) & SEED_MAX
        for stream, child in zip(SEED_STREAMS, run.spawn(5), strict=True)
    }
    assert derive_run_seeds(7, 3) == expected


def test_replications_get_different_seeds_in_every_stream() -> None:
    a, b = derive_run_seeds(42, 0), derive_run_seeds(42, 1)
    assert all(a[stream] != b[stream] for stream in SEED_STREAMS)


def test_master_seeds_differ() -> None:
    assert derive_run_seeds(1, 0) != derive_run_seeds(2, 0)


def test_streams_within_a_run_are_distinct() -> None:
    seeds = derive_run_seeds(42, 0)
    assert len(set(seeds.values())) == len(SEED_STREAMS)


def test_the_signature_admits_no_controller() -> None:
    """D-017's common random numbers at the seed level: nothing about the arm can
    reach the derivation, because the derivation cannot be told the arm."""
    assert list(inspect.signature(derive_run_seeds).parameters) == ["master_seed", "seed_index"]


def test_negative_inputs_are_refused() -> None:
    with pytest.raises(ValueError):
        derive_run_seeds(-1, 0)
    with pytest.raises(ValueError):
        derive_run_seeds(0, -1)
