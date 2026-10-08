"""Per-stream seed derivation invariants (D-017)."""

from __future__ import annotations

import inspect

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from tests.backend.conftest import Scenario, make_config
from traffic_lab.backend import SumoBackend
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


# --- SUMO's range (T1.11) ---------------------------------------------------------


def test_seed_max_is_sumos_signed_int32_limit() -> None:
    assert SEED_MAX == 2**31 - 1 == 2147483647


@settings(max_examples=500, deadline=None)
@given(master_seed=st.integers(min_value=0, max_value=2**63))
def test_every_master_seed_derives_seeds_sumo_accepts(master_seed: int) -> None:
    assert all(0 <= v <= SEED_MAX for v in derive_seeds(master_seed).values())


def test_derive_seeds_follows_the_documented_scheme() -> None:
    """The master's children, in `SEED_STREAMS` order, each its first state word
    shifted right by one bit. The two values T1.5's builder found out of SUMO's
    range -- 3757552657 and 2240297063 before the shift -- are now in it."""
    children = np.random.SeedSequence(0).spawn(5)
    expected = {
        stream: int(child.generate_state(1)[0]) >> 1
        for stream, child in zip(SEED_STREAMS, children, strict=True)
    }
    assert derive_seeds(0) == expected
    assert derive_seeds(0)["demand"] == 3757552657 >> 1
    assert derive_seeds(2)["driver"] == 2240297063 >> 1


def test_backend_config_refuses_a_seed_sumo_cannot_parse() -> None:
    """Out of range fails at config load, not at SUMO start."""
    make_config(seed=SEED_MAX)
    with pytest.raises(ValidationError, match="seed"):
        make_config(seed=SEED_MAX + 1)


@pytest.mark.parametrize("transport", ["traci", "libsumo"])
def test_sumo_starts_with_the_largest_allowed_seed(scenario: Scenario, transport: str) -> None:
    """`start()` reads `--seed` back from the running simulator and raises if it
    did not arrive intact, so a clean start and a step are the proof."""
    backend = SumoBackend()
    backend.start(
        scenario.net,
        scenario.routes,
        make_config(transport=transport, seed=SEED_MAX),
        network=scenario.network,
    )
    try:
        backend.step()
        assert backend.project().time_s == 1.0
    finally:
        backend.close()


# --- derive_run_seeds (T1.11) ----------------------------------------------------


@settings(max_examples=500, deadline=None)
@given(master_seed=st.integers(min_value=0, max_value=2**63), seed_index=st.integers(0, 10_000))
def test_run_seeds_cover_every_stream_within_sumos_range(master_seed: int, seed_index: int) -> None:
    seeds = derive_run_seeds(master_seed, seed_index)
    assert set(seeds) == set(SEED_STREAMS)
    assert all(0 <= v <= SEED_MAX for v in seeds.values())


def test_run_seeds_are_deterministic() -> None:
    assert derive_run_seeds(42, 3) == derive_run_seeds(42, 3)


def test_run_seeds_follow_the_documented_scheme() -> None:
    """The run is the `seed_index`-th spawned child of the master; the streams are
    that run's children, in `SEED_STREAMS` order, each its first state word
    shifted right by one bit."""
    run = np.random.SeedSequence(7).spawn(4)[3]
    expected = {
        stream: int(child.generate_state(1)[0]) >> 1
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
