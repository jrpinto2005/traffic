# M0 Performance — transport and query strategy

**Ticket:** `tickets/M0/T0.3_performance.md` · **Status:** complete

---

## Method

Hardware: Apple M3, macOS arm64, Python 3.12.1.

The benchmark uses the reference scenario in `spikes/M0_reference/` and queries the fields M1 will actually need on every step:

- per vehicle: position, speed, type, lane id, `timeLoss`, `waitingTime`
- per lane: halting count, occupancy, vehicle count
- per signal: current state

Four combinations were measured:

1. TraCI + polling
2. TraCI + subscriptions
3. LibSUMO + polling
4. LibSUMO + subscriptions

Each combination was run **twice**. Two samples do not support a standard deviation, so the
spread below is indicative only and should not be read as an uncertainty estimate. Independently
reproduced by the architect on 2026-08-18: TraCI/polling 71.05 s, TraCI/subscriptions 7.30 s,
LibSUMO/polling 1.49 s, LibSUMO/subscriptions 2.57 s — the same ordering, so the finding below
is robust despite the thin replication.

---

## Results

| Backend | Query strategy | Wall-clock / simulated hour |
| --- | --- | --- |
| TraCI | polling | 71.39 s ± 0.06 |
| TraCI | subscriptions | 7.08 s ± 0.06 |
| LibSUMO | polling | 1.43 s ± 0.01 |
| LibSUMO | subscriptions | 2.42 s ± 0.00 |

---

## Conclusion

**`D-002` is strongly confirmed.** LibSUMO is roughly 28× faster than TraCI on the best
strategy available to each, and roughly 48× faster on the naive one. The seam is worth having.

**`D-031`'s subscription rule is confirmed for TraCI and contradicted for LibSUMO.**

| Transport | Subscriptions vs polling |
| --- | --- |
| TraCI | **~10× faster** — subscriptions are essential |
| LibSUMO | **~1.7× slower** — subscriptions are a net cost |

This is not an anomaly, it is the expected consequence of the mechanism. `D-031` made
subscriptions an *architectural constraint* on the stated grounds that "round-trips dominate".
That is a property of TraCI's socket. LibSUMO is an in-process binding with no socket, so
subscription bookkeeping buys nothing and costs something.

It matters because LibSUMO is the transport intended for **every heavy workload** — the M5
sweeps and the M7 training runs.

### Escalated, not decided here

An earlier version of this document resolved the tension itself, arguing that subscriptions
remain right "because they are the correct seam for later sensor/model work". That is an
architect's decision, and `08_AGENT_HANDOFF_PROTOCOL.md` §8 requires it be escalated rather
than settled by a spike. It has been escalated; see `D-031` for the amended rule.

The substantive point that survives is narrower than the original rule: what must be preserved
is **one batched projection per step with no per-object access exposed to other layers**. The
*mechanism* for batching is transport-specific. Context subscriptions remain the right tool for
M3's radius queries, which are a different question from per-step whole-state projection.

The benchmark script is `spikes/M0_reference/bench_performance.py`.
