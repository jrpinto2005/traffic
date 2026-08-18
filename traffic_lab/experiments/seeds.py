"""Per-stream seed derivation from one master seed (D-017).

07_EXPERIMENT_METHODOLOGY.md SS6.1 names five independent sources of randomness:
demand, driver, sensor, estimator, policy. Independence between streams is what
makes ablations interpretable (hold `demand` fixed while varying `sensor` to isolate
the sensing effect); a single global seed makes that impossible.

Only the `demand` stream has a consumer at T1.1 (T1.5 builds the demand generator).
All five are still derived and recorded here because the manifest field is per
D-017 "all of them, always", not per what happens to be wired up yet.
"""

from __future__ import annotations

import numpy as np

SEED_STREAMS: tuple[str, ...] = ("demand", "driver", "sensor", "estimator", "policy")


def derive_seeds(master_seed: int) -> dict[str, int]:
    """Derive one independent seed per stream in `SEED_STREAMS` from `master_seed`.

    Uses `numpy.random.SeedSequence` spawning: a documented, deterministic algorithm
    (not dependent on machine, process, or wall-clock state) that produces
    statistically independent child streams from one entropy source. The same
    `master_seed` therefore always derives the same per-stream seeds, on any
    machine, which is what lets D-017's common-random-numbers design and paired
    comparisons hold across arms and across reruns.

    Stream order is fixed by `SEED_STREAMS`, so adding a stream in the future
    changes nothing about the seeds already derived for earlier streams.
    """
    parent = np.random.SeedSequence(master_seed)
    children = parent.spawn(len(SEED_STREAMS))
    return {
        stream: int(child.generate_state(1)[0])
        for stream, child in zip(SEED_STREAMS, children, strict=True)
    }
