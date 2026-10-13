"""Per-stream seed derivation from one master seed (D-017).

07_EXPERIMENT_METHODOLOGY.md SS6.1 names five independent sources of randomness:
demand, driver, sensor, estimator, policy. Independence between streams is what
makes ablations interpretable (hold `demand` fixed while varying `sensor` to isolate
the sensing effect); a single global seed makes that impossible.

All five are derived and recorded because the manifest field is per D-017 "all of
them, always", not per what happens to be wired up yet.

**Every stream seed lies in `[0, SEED_MAX]`.** SUMO and `jtrrouter` parse `--seed`
as a signed 32-bit integer: 2147483647 is accepted, 2147483648 is rejected as
"not a valid integer" (measured, SUMO 1.27.1). A stream's seed is therefore the
first 32-bit word of its `SeedSequence` child's state **shifted right by one
bit** -- a deterministic function of that child alone, so a stream's seed still
depends on nothing but the master seed, its replication and its own position.
"""

from __future__ import annotations

import numpy as np

SEED_STREAMS: tuple[str, ...] = ("demand", "driver", "sensor", "estimator", "policy")

#: The largest seed SUMO and `jtrrouter` accept: their `--seed` is a signed int32.
SEED_MAX = 2**31 - 1


def _stream_seed(child: np.random.SeedSequence) -> int:
    """The first 32-bit word of `child`'s state, shifted right by one: `[0, SEED_MAX]`."""
    return int(child.generate_state(1, dtype=np.uint32)[0]) >> 1


def derive_seeds(master_seed: int) -> dict[str, int]:
    """Derive one independent seed per stream in `SEED_STREAMS` from `master_seed`.

    Uses `numpy.random.SeedSequence` spawning: a documented, deterministic algorithm
    (not dependent on machine, process, or wall-clock state) that produces
    statistically independent child streams from one entropy source. The same
    `master_seed` therefore always derives the same per-stream seeds, on any
    machine, which is what lets D-017's common-random-numbers design and paired
    comparisons hold across arms and across reruns. Each seed is cut to SUMO's
    range as the module docstring describes.

    Stream order is fixed by `SEED_STREAMS`, so adding a stream in the future
    changes nothing about the seeds already derived for earlier streams.
    """
    parent = np.random.SeedSequence(master_seed)
    children = parent.spawn(len(SEED_STREAMS))
    return {
        stream: _stream_seed(child) for stream, child in zip(SEED_STREAMS, children, strict=True)
    }


def derive_run_seeds(master_seed: int, seed_index: int) -> dict[str, int]:
    """Per-stream seeds for replication `seed_index` of an experiment (D-017).

    The documented scheme, in two levels of `numpy.random.SeedSequence` spawning:

    1. **The run.** `SeedSequence(master_seed, spawn_key=(seed_index,))` -- by
       NumPy's definition exactly the `seed_index`-th child that
       `SeedSequence(master_seed).spawn(...)` would return, computed without
       spawning the ones before it.
    2. **The streams.** That run's sequence spawns one child per entry of
       `SEED_STREAMS`, in that order; each stream's seed is the first 32-bit
       word of its child's state shifted right by one bit (`[0, SEED_MAX]`).

    It deliberately takes no controller. The same `(master_seed, seed_index)`
    gives every arm of a comparison the same five streams -- the seed-level half
    of D-017's common random numbers -- and the streams are independent of one
    another, so any one can be held fixed while another varies. `driver` is
    SUMO's `--seed`; the others are recorded in the run manifest.
    """
    if master_seed < 0 or seed_index < 0:
        raise ValueError(
            f"master_seed and seed_index must be non-negative, got {master_seed}, {seed_index}"
        )
    run = np.random.SeedSequence(master_seed, spawn_key=(seed_index,))
    return {
        stream: _stream_seed(child)
        for stream, child in zip(SEED_STREAMS, run.spawn(len(SEED_STREAMS)), strict=True)
    }
